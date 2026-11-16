"""TableFlow ELT: PostgreSQL (operational) -> Snowflake (analytical).

    Extract   incremental rows from PostgreSQL (watermark on updated_at/created_at) to CSV
    Load      Snowflake:  PUT file://... @RAW.TF_STAGE ; COPY INTO RAW.<table>
    Transform run snowflake/transformations/*.sql inside the warehouse (ELT, not ETL)

Two modes, chosen automatically and printed loudly:

* SNOWFLAKE mode - when SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and SNOWFLAKE_PRIVATE_KEY_PATH are set
  and `snowflake-connector-python` is installed. Authenticates with RSA key-pair (no password).
* LOCAL DEMO mode - otherwise. Loads the same CSVs into a local DuckDB file and runs the *same*
  transformation SQL, so the modelling can be demonstrated. This is NOT Snowflake and the output
  says so; nothing is claimed to have reached a Snowflake account.

Usage (from repo root):
    DATABASE_URL=postgresql://tableflow:tableflow@localhost:5432/tableflow python snowflake/etl/extract_load.py
    python snowflake/etl/extract_load.py --full          # ignore watermark, re-extract everything
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "sample_data"
STATE = ROOT / "etl" / ".watermarks.json"
TZ = "Africa/Johannesburg"

# table -> (SELECT ..., watermark column)  business_date computed in SAST at extract time
EXTRACTS = {
    "branches": ("SELECT id, code, name, city, province, is_active, opened_on FROM branches", None),
    "products": ("SELECT id, sku, name, category, price FROM products", None),
    "orders": (f"SELECT id, order_number, branch_id, customer_id, channel, status, subtotal, vat, total, created_at, "
               f"(created_at AT TIME ZONE '{TZ}')::date AS business_date, updated_at FROM orders", "updated_at"),
    "order_items": ("SELECT i.id, i.order_id, i.product_id, i.quantity, i.unit_price, i.line_total FROM order_items i "
                    "JOIN orders o ON o.id = i.order_id", "o.updated_at"),
    "payments": (f"SELECT id, order_id, provider_reference, amount, method, status, failure_reason, refunded_amount, "
                 f"created_at, (created_at AT TIME ZONE '{TZ}')::date AS business_date, updated_at FROM payments",
                 "updated_at"),
    "loyalty_transactions": (f"SELECT id, account_id, order_id, type, points, sync_status, created_at, "
                             f"(created_at AT TIME ZONE '{TZ}')::date AS business_date FROM loyalty_transactions",
                             "created_at"),
    "integration_logs": (f"SELECT l.id, i.name AS integration, l.operation, l.status, l.response_ms, l.attempt, "
                         f"l.created_at, (l.created_at AT TIME ZONE '{TZ}')::date AS business_date "
                         f"FROM integration_logs l JOIN integrations i ON i.id = l.integration_id", "l.created_at"),
}


def pg_url() -> str:
    url = os.getenv("DATABASE_URL", "postgresql://tableflow:tableflow@localhost:5432/tableflow")
    return url.replace("postgresql+psycopg://", "postgresql://")


def extract(full: bool) -> dict[str, Path]:
    import psycopg

    marks = {} if full or not STATE.exists() else json.loads(STATE.read_text())
    run_at = datetime.now(timezone.utc)
    # Full extracts refresh the committed sample dataset; incremental extracts go to their own folder
    # (bug found in testing: an incremental run used to overwrite the sample CSVs with empty files).
    out_dir = DATA if full else ROOT / "etl" / "extracts" / run_at.strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {}
    with psycopg.connect(pg_url()) as conn:
        for table, (sql, wm_col) in EXTRACTS.items():
            params = ()
            if wm_col and table in marks:
                sql += f" WHERE {wm_col} > %s"
                params = (marks[table],)
            with conn.cursor() as cur:
                cur.execute(sql + " ORDER BY 1", params)
                cols = [d.name for d in cur.description] + ["_extracted_at"]
                rows = cur.fetchall()
            path = out_dir / f"{table}.csv"
            with path.open("w", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(cols)
                for r in rows:
                    w.writerow([*("" if v is None else v for v in r), run_at.isoformat()])
            files[table] = path
            print(f"  extracted {table:<22} {len(rows):>7} rows -> {path.relative_to(ROOT.parent)}")
            marks[table] = run_at.isoformat()
    STATE.write_text(json.dumps(marks, indent=2))
    return files


def sql_statements(path: Path) -> list[str]:
    text = re.sub(r"--[^\n]*", "", path.read_text())
    return [s.strip() for s in text.split(";") if s.strip()]


def snowflake_configured() -> bool:
    need = ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PRIVATE_KEY_PATH")
    if not all(os.getenv(k) for k in need):
        return False
    try:
        import snowflake.connector  # noqa: F401
    except ImportError:
        print("  snowflake-connector-python not installed -> falling back to local demo mode")
        return False
    return True


def load_snowflake(files: dict[str, Path], full: bool) -> None:  # pragma: no cover - needs a real account
    import snowflake.connector

    sys.path.insert(0, str(ROOT.parent / "backend"))
    from app.security.keypair import private_key_der

    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
        private_key=private_key_der(os.environ["SNOWFLAKE_PRIVATE_KEY_PATH"],
                                    os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None),
        warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "TABLEFLOW_WH"),
        database=os.getenv("SNOWFLAKE_DATABASE", "TABLEFLOW_ANALYTICS"),
        role=os.getenv("SNOWFLAKE_ROLE", "TABLEFLOW_LOADER"), schema="RAW")
    cur = conn.cursor()
    for stmt in sql_statements(ROOT / "schemas" / "02_raw_tables.sql"):
        cur.execute(stmt)
    for table, path in files.items():
        if full or table in ("branches", "products"):
            cur.execute(f"TRUNCATE TABLE IF EXISTS RAW.{table.upper()}")
        cur.execute(f"PUT file://{path} @RAW.TF_STAGE/{table} AUTO_COMPRESS=TRUE OVERWRITE=TRUE")
        cur.execute(f"COPY INTO RAW.{table.upper()} FROM @RAW.TF_STAGE/{table} FILE_FORMAT=(FORMAT_NAME=RAW.CSV_TF) "
                    f"ON_ERROR=ABORT_STATEMENT PURGE=TRUE")
        print(f"  loaded {table} into Snowflake RAW")
    for f in sorted((ROOT / "transformations").glob("*.sql")):
        for stmt in sql_statements(f):
            cur.execute(stmt)
        print(f"  ran {f.name} in Snowflake")
    conn.close()


def load_local(files: dict[str, Path], db_path: Path) -> None:
    import duckdb

    con = duckdb.connect(str(db_path))
    for stmt in sql_statements(ROOT / "schemas" / "02_raw_tables.sql"):
        con.execute(stmt)
    for table, path in files.items():
        if table in ("branches", "products"):
            con.execute(f"DELETE FROM raw.{table}")
        con.execute(f"INSERT INTO raw.{table} SELECT * FROM read_csv('{path}', header=true, auto_detect=true, "
                    f"nullstr='')")
    for f in sorted((ROOT / "transformations").glob("*.sql")):
        for stmt in sql_statements(f):
            con.execute(stmt)
        print(f"  ran {f.name} (DuckDB)")
    print("\n  Sample analytical query results (snowflake/queries/analytical_queries.sql):")
    text = (ROOT / "queries" / "analytical_queries.sql").read_text()
    for block in re.split(r"(?m)^-- name: ", text)[1:]:
        name, sql = block.split("\n", 1)
        rows = con.execute(sql.strip().rstrip(";")).fetchall()
        print(f"   - {name.strip():<28} {len(rows):>4} rows  e.g. {rows[0] if rows else '()'}")
    for t in ("analytics.mart_daily_branch_sales", "analytics.fct_orders", "analytics.fct_payments"):
        print(f"   {t:<36} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>7} rows")
    con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="ignore watermarks and re-extract everything")
    ap.add_argument("--duckdb", default=str(ROOT / "etl" / "tableflow_local.duckdb"))
    a = ap.parse_args()
    mode = "SNOWFLAKE" if snowflake_configured() else "LOCAL DEMO (DuckDB - not Snowflake)"
    print(f"TableFlow ELT - mode: {mode}")
    print("[1/3] Extract from PostgreSQL")
    files = extract(a.full)
    print("[2/3] Load + [3/3] Transform")
    if mode == "SNOWFLAKE":
        load_snowflake(files, a.full)
    else:
        if a.full and Path(a.duckdb).exists():
            Path(a.duckdb).unlink()
        load_local(files, Path(a.duckdb))
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
