#!/bin/sh
# Apply SQL migrations, seed demo data once (only when SEED_DEMO_DATA=true and DB empty), then start the API.
set -e
echo "[entrypoint] applying migrations"
python -m app.migrate
if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  echo "[entrypoint] seeding demo data if empty"
  python -m app.seed --if-empty --days "${SEED_DAYS:-60}"
fi
exec "$@"
