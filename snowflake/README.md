# Snowflake analytics

| Path | Purpose |
|---|---|
| `schemas/01_account_setup.sql` | warehouse, database, RAW/STAGING/ANALYTICS schemas, roles, key-pair service user, stage |
| `schemas/02_raw_tables.sql` | landing tables |
| `transformations/01_staging.sql` | de-dup latest version (QUALIFY), flags |
| `transformations/02_analytics_marts.sql` | dims, facts, reporting marts |
| `queries/analytical_queries.sql` | 9 business questions |
| `etl/extract_load.py` | incremental extract from PostgreSQL → Snowflake (PUT/COPY) or local DuckDB demo |
| `sample_data/*.csv` | full extract of the seeded dataset |

**Live mode** needs `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PRIVATE_KEY_PATH` and
`pip install snowflake-connector-python`; generate keys with `python -m app.security.keypair ./keys` (from `backend/`).
Without them the script prints `mode: LOCAL DEMO (DuckDB - not Snowflake)` — no Snowflake connection is claimed.
