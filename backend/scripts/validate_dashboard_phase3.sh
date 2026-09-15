#!/usr/bin/env bash
# Exact-source Phase 3 staging validation. It refuses a backend .env, clears
# inherited application configuration, and uses only a verified socket-local
# temporary PostgreSQL database. It never targets a production service, web
# root, backup, APK, or configured application database.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

fail() { echo "FAIL: $*" >&2; exit 1; }

pg_bin="${PHASE3_PG_BIN:-/usr/lib/postgresql/14/bin}"
external_socket="${PHASE3_EXISTING_TEST_SOCKET:-}"
external_database="${PHASE3_EXISTING_TEST_DATABASE:-}"
server_started=0
owns_cluster=0
pg_run=()

[[ ! -e .env && ! -L .env ]] || \
  fail "backend/.env is forbidden during detached Phase 3 staging"
for command in openssl mktemp sed grep; do
  command -v "$command" >/dev/null || fail "required command not found: $command"
done
for command in initdb pg_ctl createdb psql pg_isready; do
  [[ -x "$pg_bin/$command" ]] || fail "PostgreSQL tool is missing: $pg_bin/$command"
done

# Never inherit a production URL or secret. Pydantic environment variables set
# below take precedence, and the absent .env prevents a configuration fallback.
unset DATABASE_URL APEX_DASHBOARD_TEST_DATABASE_URL APP_ENV JWT_SECRET

if [[ -n "$external_socket" || -n "$external_database" ]]; then
  [[ -n "$external_socket" && -n "$external_database" ]] || \
    fail "both existing test socket and database must be supplied"
  [[ "$external_socket" == /tmp/apex-phase3-validation-* ]] || \
    fail "existing test socket is outside the protected Phase 3 prefix"
  [[ "$external_database" == apexretail_phase2_test_* ]] || \
    fail "existing database lacks the isolated test prefix"
  test_root="$external_socket"
else
  test_root=$(mktemp -d /tmp/apex-phase3-validation-XXXXXX)
  external_database="apexretail_phase2_test_fresh"
  owns_cluster=1
fi

if [[ $(id -u) == 0 ]]; then
  [[ "$owns_cluster" -eq 0 ]] || chown postgres:postgres "$test_root"
  pg_run=(runuser -u postgres --)
fi

cleanup() {
  local status=$?
  trap - EXIT INT TERM
  set +e
  unset DATABASE_URL APEX_DASHBOARD_TEST_DATABASE_URL APP_ENV JWT_SECRET
  if [[ "$owns_cluster" -eq 1 && "$server_started" -eq 1 ]]; then
    "${pg_run[@]}" "$pg_bin/pg_ctl" -D "$test_root/data" -m immediate -w stop >/dev/null
    stop_status=$?
    if [[ "$stop_status" -ne 0 ]]; then
      echo "FAIL: temporary PostgreSQL did not stop cleanly" >&2
      status=1
    fi
  fi
  if [[ "$owns_cluster" -eq 1 ]]; then
    if [[ -e "$test_root/data/postmaster.pid" || -S "$test_root/.s.PGSQL.5432" ]]; then
      echo "FAIL: temporary PostgreSQL PID or socket remains" >&2
      status=1
    else
      echo "PASS: temporary PostgreSQL stopped; no PID or socket remains"
    fi
  fi
  echo "Temporary validation artifacts: $test_root"
  exit "$status"
}
trap cleanup EXIT INT TERM

if [[ "$owns_cluster" -eq 1 ]]; then
  "${pg_run[@]}" "$pg_bin/initdb" -D "$test_root/data" -U postgres -A trust >"$test_root/initdb.log"
  "${pg_run[@]}" "$pg_bin/pg_ctl" -D "$test_root/data" -l "$test_root/postgres.log" -o "-k $test_root -c listen_addresses=''" -w start
  server_started=1
  "${pg_run[@]}" "$pg_bin/createdb" --host="$test_root" --username=postgres "$external_database"
fi

export PGHOST="$test_root" PGUSER=postgres PGPORT=5432
export APP_ENV=test
export JWT_SECRET
JWT_SECRET="$(openssl rand -hex 32)"
export DATABASE_URL="postgresql+asyncpg://postgres@/${external_database}?host=${test_root}"
export APEX_DASHBOARD_TEST_DATABASE_URL="$DATABASE_URL"

"$pg_bin/pg_isready" --host="$test_root" --dbname="$external_database" --quiet || \
  fail "isolated PostgreSQL is unavailable before migrations"
identity="$("$pg_bin/psql" --host="$test_root" --username=postgres --dbname="$external_database" -XAt --no-psqlrc -v ON_ERROR_STOP=1 \
  -c "SELECT current_database() || '|' || (inet_server_addr() IS NULL)::text || '|' || current_setting('data_directory');")" || \
  fail "isolated PostgreSQL identity query failed before migrations"
IFS='|' read -r actual_database socket_only actual_data_directory <<<"$identity"
[[ "$actual_database" == "$external_database" ]] || fail "isolated database identity mismatch"
[[ "$socket_only" == true ]] || fail "isolated PostgreSQL unexpectedly has a TCP server address"
[[ "$actual_data_directory" == "$test_root/data" ]] || fail "isolated PostgreSQL data directory mismatch"
echo "PASS: isolated database identity verified before migrations: $actual_database"

[[ "$owns_cluster" -eq 1 ]] || fail "existing isolated database mode is probe-only"
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

export DATABASE_URL="postgresql+asyncpg://postgres@/apexretail_phase2_test_fresh?host=$test_root"
export APEX_DASHBOARD_TEST_DATABASE_URL="$DATABASE_URL"
venv/bin/python -m alembic upgrade head
PYTHONPATH=. venv/bin/python scripts/measure_phase3_dashboard.py
venv/bin/python -m unittest discover -s tests -v
"$pg_bin/psql" -d apexretail_phase2_test_fresh -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN
  ASSERT (SELECT count(*)=0 FROM sales), 'Tests or measurements leaked sales';
  ASSERT (SELECT count(*)=0 FROM companies), 'Tests or measurements leaked companies';
END $$;
SQL
echo 'PASS: Phase 2 clone cycle, fresh migrations, Phase 3 measurements, backend suite, and rollback isolation'
