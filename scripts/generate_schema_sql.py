"""Generate database/migrations/V001__initial_schema.sql from the SQLAlchemy models.

Run once when the models change *before first release*; after a migration has
been applied anywhere, never regenerate it - add a new V00N file instead.
The test-suite (tests/test_migrations.py) proves the migrated PostgreSQL schema
matches the ORM models, so drift is caught in CI.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

import app.models  # noqa: E402,F401
from app.database import Base  # noqa: E402

dialect = postgresql.dialect()
parts = ["-- V001: initial TableFlow Enterprise schema (generated from backend/app/models by",
         "-- scripts/generate_schema_sql.py). PostgreSQL 14+.", ""]
for table in Base.metadata.sorted_tables:
    parts.append(f"-- {table.name}" + (f": {table.comment}" if table.comment else ""))
    parts.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
    for idx in sorted(table.indexes, key=lambda i: i.name):
        parts.append(str(CreateIndex(idx).compile(dialect=dialect)).strip() + ";")
    parts.append("")
out = ROOT / "database" / "migrations" / "V001__initial_schema.sql"
out.write_text("\n".join(parts))
print(f"wrote {out}")
