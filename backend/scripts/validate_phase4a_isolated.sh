#!/usr/bin/env bash
set -Eeuo pipefail

source_backend="$(cd "$(dirname "$0")/.." && pwd)"
source_root="$(cd "$source_backend/.." && pwd)"
pg_bin="${PHASE4A_PG_BIN:-/usr/lib/postgresql/14/bin}"
test_root="$(mktemp -d /tmp/apex-phase4a-validation-XXXXXX)"
stage_root="$test_root/source"
stage="$stage_root/backend"
server_started=0

cleanup() {
  status=$?
  trap - EXIT INT TERM
  set +e
  if [[ "$server_started" -eq 1 ]]; then
    runuser -u postgres -- "$pg_bin/pg_ctl" -D "$test_root/data" -m immediate -w stop >/dev/null
    [[ $? -eq 0 ]] || status=1
  fi
  if [[ -e "$test_root/data/postmaster.pid" || -S "$test_root/.s.PGSQL.5432" ]]; then
    echo "FAIL: temporary PostgreSQL process or socket remains" >&2
    status=1
  else
    echo "PASS: temporary PostgreSQL stopped with no remaining socket or PID"
  fi
  echo "Temporary validation artifacts: $test_root"
  exit "$status"
}
trap cleanup EXIT INT TERM

for command in initdb pg_ctl createdb psql pg_isready; do
  [[ -x "$pg_bin/$command" ]] || { echo "Missing PostgreSQL tool: $command" >&2; exit 1; }
done
command -v rsync >/dev/null
command -v openssl >/dev/null

mkdir "$stage_root"
rsync -a --exclude='.git' --exclude='.env*' --exclude='venv' \
  --exclude='node_modules' --exclude='dist' --exclude='backups' \
  --exclude='__pycache__' "$source_root/" "$stage_root/"
ln -s "$source_backend/venv" "$stage/venv"
chown postgres:postgres "$test_root"
runuser -u postgres -- "$pg_bin/initdb" -D "$test_root/data" -U postgres -A trust >"$test_root/initdb.log"
runuser -u postgres -- "$pg_bin/pg_ctl" -D "$test_root/data" -l "$test_root/postgres.log" -o "-k $test_root -c listen_addresses=''" -w start
server_started=1

export PGHOST="$test_root" PGUSER=postgres PGPORT=5432
export APP_ENV=test JWT_SECRET
JWT_SECRET="$(openssl rand -hex 32)"
unset PAYNOW_INTEGRATION_ID PAYNOW_INTEGRATION_KEY SUBSCRIPTION_PROVIDER_CHECKOUT_BASE_URL

phase4_db="apexretail_phase4a_test_fresh"
phase2_db="apexretail_phase2_test_phase4a"
"$pg_bin/createdb" "$phase4_db"
"$pg_bin/createdb" "$phase2_db"

cd "$stage"
export DATABASE_URL="postgresql+asyncpg://postgres@/$phase4_db?host=$test_root"
export APEX_PHASE4A_TEST_DATABASE_URL="$DATABASE_URL"
venv/bin/python -m alembic upgrade head
venv/bin/python -m unittest -v tests.test_phase4a_postgres
PYTHONPATH=. venv/bin/python scripts/measure_phase4a_reports.py | tee "$test_root/phase4a-query-plans.json"

venv/bin/python -m alembic downgrade d4discountcomponents
"$pg_bin/psql" -XAt --no-psqlrc -v ON_ERROR_STOP=1 -d "$phase4_db" -c "SELECT count(*)=0 FROM information_schema.columns WHERE table_name='sale_items' AND column_name IN ('category_id_snapshot','category_name_snapshot','cost_snapshot_available');" | grep -qx t
venv/bin/python -m alembic upgrade head
"$pg_bin/psql" -XAt --no-psqlrc -v ON_ERROR_STOP=1 -d "$phase4_db" -c "SELECT count(*)=3 AND bool_and(is_nullable='YES') FROM information_schema.columns WHERE table_name='sale_items' AND column_name IN ('category_id_snapshot','category_name_snapshot','cost_snapshot_available');" | grep -qx t
venv/bin/python -m unittest -v tests.test_phase4a_postgres

export DATABASE_URL="postgresql+asyncpg://postgres@/$phase2_db?host=$test_root"
export APEX_DASHBOARD_TEST_DATABASE_URL="$DATABASE_URL"
venv/bin/python -m alembic upgrade head
venv/bin/python -m unittest discover -s tests -v

"$pg_bin/psql" -XAt --no-psqlrc -v ON_ERROR_STOP=1 -d "$phase4_db" -c "SELECT count(*) FROM companies;" | grep -qx 0
"$pg_bin/psql" -XAt --no-psqlrc -v ON_ERROR_STOP=1 -d "$phase2_db" -c "SELECT count(*) FROM companies;" | grep -qx 0
echo "PASS: Phase 4A migration cycle, PostgreSQL integration, query plans, full backend suite, and rollback isolation"
