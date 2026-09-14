#!/usr/bin/env bash
# New socket-only PostgreSQL cluster with synthetic records. Never targets an
# existing database, production service, web root, backup, or APK.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
pg_bin="${PHASE3_PG_BIN:-/usr/lib/postgresql/14/bin}"
test_root=$(mktemp -d /tmp/apex-phase3-validation-XXXXXX)
pg_run=()
if [[ $(id -u) == 0 ]]; then
  chown postgres:postgres "$test_root"
  pg_run=(runuser -u postgres --)
fi
cleanup() {
  "${pg_run[@]}" "$pg_bin/pg_ctl" -D "$test_root/data" -m immediate -w stop >/dev/null || true
  echo "Temporary validation artifacts: $test_root"
}
trap cleanup EXIT
"${pg_run[@]}" "$pg_bin/initdb" -D "$test_root/data" -U postgres -A trust >"$test_root/initdb.log"
"${pg_run[@]}" "$pg_bin/pg_ctl" -D "$test_root/data" -l "$test_root/postgres.log" -o "-k $test_root -c listen_addresses=''" -w start
export PGHOST="$test_root" PGUSER=postgres PGPORT=5432
export APP_ENV=test JWT_SECRET=phase3-isolated-validation-only

"$pg_bin/createdb" apexretail_phase2_test_baseline
export DATABASE_URL="postgresql+asyncpg://postgres@/apexretail_phase2_test_baseline?host=$test_root"
venv/bin/python -m alembic upgrade c2phase1inventory
"$pg_bin/psql" -d apexretail_phase2_test_baseline -v ON_ERROR_STOP=1 <<'SQL'
INSERT INTO sales (id, company_id, receipt_number, total_amount, amount_received, change_due, payment_method, status)
VALUES ('11111111-1111-1111-1111-111111111111', '22222222-2222-2222-2222-222222222222', 'PHASE3-HISTORICAL', 12, 12, 0, 'cash', 'completed');
SQL
"$pg_bin/createdb" -T apexretail_phase2_test_baseline apexretail_phase2_test_clone
export DATABASE_URL="postgresql+asyncpg://postgres@/apexretail_phase2_test_clone?host=$test_root"
venv/bin/python -m alembic upgrade head
"$pg_bin/psql" -d apexretail_phase2_test_clone -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN
  ASSERT (SELECT discount_amount IS NULL AND sale_discount_amount IS NULL AND total_amount=12 FROM sales WHERE receipt_number='PHASE3-HISTORICAL'), 'Historical sale changed';
  ASSERT (SELECT is_nullable='YES' AND column_default IS NULL FROM information_schema.columns WHERE table_name='sale_items' AND column_name='line_discount_amount'), 'Unexpected line discount default';
END $$;
SQL
venv/bin/python -m alembic downgrade c2phase1inventory
venv/bin/python -m alembic upgrade head

"$pg_bin/createdb" apexretail_phase2_test_fresh
export DATABASE_URL="postgresql+asyncpg://postgres@/apexretail_phase2_test_fresh?host=$test_root"
venv/bin/python -m alembic upgrade head
PYTHONPATH=. venv/bin/python scripts/measure_phase3_dashboard.py
export APEX_DASHBOARD_TEST_DATABASE_URL="$DATABASE_URL"
venv/bin/python -m unittest discover -s tests -v
"$pg_bin/psql" -d apexretail_phase2_test_fresh -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN
  ASSERT (SELECT count(*)=0 FROM sales), 'Tests or measurements leaked sales';
  ASSERT (SELECT count(*)=0 FROM companies), 'Tests or measurements leaked companies';
END $$;
SQL
echo 'PASS: Phase 2 clone cycle, fresh migrations, Phase 3 measurements, backend suite, and rollback isolation'
