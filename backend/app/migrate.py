"""Minimal, dependency-free SQL migration runner (Flyway-style).

Applies `database/migrations/V###__description.sql` files in version order and
records each in `schema_migrations` with a checksum. A changed checksum on an
already-applied migration aborts the run - migrations are immutable once shipped;
corrections go in a new V### file.

Usage:  python -m app.migrate            (uses DATABASE_URL)
        python -m app.migrate --status
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

from sqlalchemy import text

from app.database import engine

MIGRATIONS_DIR = Path(os.getenv("MIGRATIONS_DIR", Path(__file__).resolve().parents[2] / "database" / "migrations"))


def _files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("V*__*.sql"), key=lambda p: int(p.name[1:].split("__")[0]))


def migrate(verbose: bool = True) -> list[str]:
    applied_now = []
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY, filename VARCHAR(255) NOT NULL, checksum VARCHAR(64) NOT NULL,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"""))
        done = {row.version: row.checksum for row in conn.execute(text("SELECT version, checksum FROM schema_migrations"))}
    for f in _files():
        version = int(f.name[1:].split("__")[0])
        sql = f.read_text()
        checksum = hashlib.sha256(sql.encode()).hexdigest()
        if version in done:
            if done[version] != checksum:
                raise SystemExit(f"Checksum mismatch for already-applied migration {f.name}. Create a new migration.")
            continue
        with engine.begin() as conn:  # each migration in its own transaction
            # Execute through the raw DBAPI cursor with NO parameters: otherwise the driver treats
            # literal '%' characters (e.g. in PL/pgSQL RAISE messages) as placeholders. (Bug found in testing.)
            cur = conn.connection.cursor()
            cur.execute(sql)
            cur.close()
            conn.execute(text("INSERT INTO schema_migrations (version, filename, checksum) VALUES (:v, :f, :c)"),
                         {"v": version, "f": f.name, "c": checksum})
        applied_now.append(f.name)
        if verbose:
            print(f"applied {f.name}")
    if verbose and not applied_now:
        print("database is up to date")
    return applied_now


def status() -> None:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version, filename, applied_at FROM schema_migrations ORDER BY version")).all()
    applied = {r.version for r in rows}
    for f in _files():
        v = int(f.name[1:].split("__")[0])
        print(f"{'[x]' if v in applied else '[ ]'} {f.name}")


if __name__ == "__main__":
    status() if "--status" in sys.argv else migrate()
