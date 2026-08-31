#!/usr/bin/env bash
# Read-only production / disposable-clone validation for Phase 1.
# This script must be run from the normal VPS root shell. It never writes to
# the production database: production is queried and pg_dump is the only
# production operation performed.
set -Eeuo pipefail

readonly PRODUCTION_DB="apexretail_pos"
readonly EXPECTED_PRODUCTION_REVISION="b8e51d8f4a21"
readonly TARGET_REVISION="c2phase1inventory"
readonly TEMP_PREFIX="apexretail_phase1_validation_"
readonly BACKEND_DIR="/root/apexretail-pos/backend"
readonly PYTHON_BIN="${BACKEND_DIR}/venv/bin/python"
readonly ENV_FILE="${BACKEND_DIR}/.env"
readonly INVENTORY_ANALYSIS_SCRIPT="${BACKEND_DIR}/scripts/analyze_phase1_inventory_delta.sh"

clone_db=""
fresh_db=""
backup_file=""
success=0

fail() { echo "FAIL: $*" >&2; exit 1; }

# Reject every non-validation database name before create, restore, or drop.
assert_temp_name() {
  local name="$1"
  [[ "$name" =~ ^${TEMP_PREFIX}[a-z0-9_]+$ ]] || fail "unsafe temporary database name: ${name}"
  [[ "$name" != "$PRODUCTION_DB" ]] || fail "production database name was supplied as temporary target"
  [[ "${#name}" -le 63 ]] || fail "temporary database identifier exceeds PostgreSQL limit"
}

assert_role_name() {
  local role="$1"
  # Restrict the parsed role to a conservative unquoted PostgreSQL identifier
  # before passing it to createdb/pg_restore or embedding it in SET ROLE.
  [[ "$role" =~ ^[a-z_][a-z0-9_]{0,62}$ ]] || fail "unsafe application database role"
}

db_exists_exact() {
  local name="$1"
  assert_temp_name "$name"
  sudo -u postgres psql -X -v ON_ERROR_STOP=1 -Atqc \
    "SELECT 1 FROM pg_database WHERE datname = '${name}';" \
    postgres | grep -qx 1
}

run_psql() {
  # The database argument is validated by callers; output is limited to
  # non-sensitive scalar validation values.
  local db="$1" sql="$2"
  sudo -u postgres psql -X -v ON_ERROR_STOP=1 -Atqc "$sql" "$db"
}

provision_extensions() {
  local db="$1"
  assert_temp_name "$db"
  # Extensions are provisioned only in disposable databases by postgres.
  sudo -u postgres psql -X -v ON_ERROR_STOP=1 -Atqc \
    "CREATE EXTENSION IF NOT EXISTS pgcrypto;" "$db"
}

app_role_access_check() {
  local db="$1"
  assert_temp_name "$db"
  # SET ROLE proves the application role can read and update the migration
  # marker; the transaction is rolled back so the clone remains unchanged.
  sudo -u postgres psql -X -v ON_ERROR_STOP=1 -Atqc \
    "BEGIN; SET LOCAL ROLE \"${db_user}\"; SELECT version_num FROM alembic_version; UPDATE alembic_version SET version_num = version_num; ROLLBACK;" \
    "$db" >/dev/null
}

assert_alembic_target() {
  local url="$1" expected_db="$2"
  # Parse only the database component; fail if Alembic could target production.
  APEX_VALIDATION_URL="$url" APEX_EXPECTED_DB="$expected_db" APEX_PRODUCTION_DB="$PRODUCTION_DB" \
    "$PYTHON_BIN" - <<'PY'
import os
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

u = make_url(os.environ["APEX_VALIDATION_URL"])
expected = os.environ["APEX_EXPECTED_DB"]
production = os.environ["APEX_PRODUCTION_DB"]
if u.database != expected or u.database == production:
    raise SystemExit("Alembic URL database target mismatch")
PY
}

inventory_totals() {
  local db="$1"
  # Counts, quantities and stock valuation are aggregate-only and contain no
  # customer or product-identifying data.
  run_psql "$db" "
    SELECT
      (SELECT count(*) FROM inventory_balances),
      (SELECT COALESCE(sum(quantity),0) FROM inventory_balances),
      (SELECT COALESCE(sum(ib.quantity * COALESCE(p.cost_price,0)),0)
         FROM inventory_balances ib LEFT JOIN products p ON p.id=ib.product_id),
      (SELECT count(*) FROM inventory_movements),
      (SELECT COALESCE(sum(quantity),0) FROM inventory_movements),
      (SELECT COALESCE(sum(stock_qty * COALESCE(cost_price,0)),0)
         FROM products WHERE deleted=false);"
}

cleanup() {
  local status=$?
  if [[ "$status" -eq 0 && "$success" -eq 1 ]]; then
    # Success cleanup is restricted to names created by this invocation and
    # happens only after all comparisons/tests have passed.
    if [[ -n "$clone_db" ]]; then
      assert_temp_name "$clone_db"
      db_exists_exact "$clone_db" && sudo -u postgres dropdb --if-exists "$clone_db"
    fi
    if [[ -n "$fresh_db" ]]; then
      assert_temp_name "$fresh_db"
      db_exists_exact "$fresh_db" && sudo -u postgres dropdb --if-exists "$fresh_db"
    fi
    if [[ -n "$backup_file" ]]; then
      [[ "$backup_file" == /tmp/${TEMP_PREFIX}* ]] || fail "unsafe backup path"
      rm -f -- "$backup_file"
    fi
    echo "PASS: temporary databases and backup removed after successful validation"
  else
    echo "FAIL: validation evidence was preserved. Manual cleanup (only after verifying exact names):" >&2
    [[ -n "$clone_db" ]] && echo "  sudo -u postgres dropdb '$clone_db'" >&2
    [[ -n "$fresh_db" ]] && echo "  sudo -u postgres dropdb '$fresh_db'" >&2
    [[ -n "$backup_file" ]] && echo "  rm -f '$backup_file'" >&2
  fi
  exit "$status"
}
trap cleanup EXIT

command -v sudo >/dev/null || fail "sudo is required"
command -v psql >/dev/null || fail "psql is required"
command -v pg_dump >/dev/null || fail "pg_dump is required"
command -v pg_restore >/dev/null || fail "pg_restore is required"
command -v createdb >/dev/null || fail "createdb is required"
command -v dropdb >/dev/null || fail "dropdb is required"
[[ -x "$PYTHON_BIN" ]] || fail "backend virtualenv Python not found"
[[ -x "$INVENTORY_ANALYSIS_SCRIPT" ]] || fail "inventory analysis script not found"
# Keep postgres commands out of /root-owned paths to avoid harmless cwd errors.
cd /tmp

# Confirm production identity before any temporary database operation.
prod_name="$(run_psql postgres "SELECT current_database();")"
[[ "$prod_name" == "postgres" ]] || fail "administrative connection did not reach postgres database"
prod_exists="$(run_psql postgres "SELECT 1 FROM pg_database WHERE datname='${PRODUCTION_DB}';")"
[[ "$prod_exists" == 1 ]] || fail "production database ${PRODUCTION_DB} was not found"
prod_revision="$(run_psql "$PRODUCTION_DB" "SELECT version_num FROM alembic_version;")"
[[ "$prod_revision" == "$EXPECTED_PRODUCTION_REVISION" ]] || fail "production revision is ${prod_revision}, expected ${EXPECTED_PRODUCTION_REVISION}"
before_totals="$(inventory_totals "$PRODUCTION_DB")"

# Build clone connection details in memory. The URL, username and password
# are never printed; only its database name is used in status messages.
db_user="$(APEX_ENV_FILE="$ENV_FILE" "$PYTHON_BIN" - <<'PY'
import os
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
u = make_url(dotenv_values(os.environ["APEX_ENV_FILE"])["DATABASE_URL"])
print(u.username or '')
PY
)"
assert_role_name "$db_user"

stamp="$(date -u +%Y%m%d%H%M%S)"
suffix="${stamp}_$RANDOM"
clone_db="${TEMP_PREFIX}clone_${suffix}"
fresh_db="${TEMP_PREFIX}fresh_${suffix}"
assert_temp_name "$clone_db"
assert_temp_name "$fresh_db"
[[ "$clone_db" != "$fresh_db" ]] || fail "temporary database names collided"

backup_file="$(mktemp "/tmp/${TEMP_PREFIX}backup_XXXXXX.dump")"
chmod 600 "$backup_file"
chown postgres:postgres "$backup_file"
umask 077
[[ "$(stat -c '%a' "$backup_file")" == 600 ]] || fail "backup permissions are not 600"

echo "Production revision: ${prod_revision}"
echo "Production aggregate inventory totals: ${before_totals}"
echo "Creating clone database: ${clone_db}"
assert_temp_name "$clone_db"
if db_exists_exact "$clone_db"; then
  fail "clone database name already exists: ${clone_db}"
fi
sudo -u postgres createdb --owner="$db_user" "$clone_db"
db_exists_exact "$clone_db" || fail "clone database was not created exactly"
provision_extensions "$clone_db"

# pg_dump is the sole operation against production that can read the full
# database; it does not modify production.
echo "Creating restricted-permission production backup"
sudo -u postgres pg_dump --format=custom --no-owner --file="$backup_file" "$PRODUCTION_DB"
[[ -s "$backup_file" ]] || fail "backup file is empty"
[[ "$(stat -c '%a' "$backup_file")" == 600 ]] || fail "backup permissions changed"

assert_temp_name "$clone_db"
db_exists_exact "$clone_db" || fail "clone disappeared before restore"
sudo -u postgres pg_restore --exit-on-error --no-owner --no-comments --no-privileges \
  --role="$db_user" --dbname="$clone_db" "$backup_file"
app_role_access_check "$clone_db"
clone_before="$(inventory_totals "$clone_db")"
[[ "$clone_before" == "$before_totals" ]] || fail "restored clone inventory differs before migration"

# Alembic receives only a clone URL. Production URL is never passed to it.
clone_url="$(APEX_ENV_FILE="$ENV_FILE" "$PYTHON_BIN" - "$clone_db" <<'PY'
import sys
import os
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
u = make_url(dotenv_values(os.environ["APEX_ENV_FILE"])["DATABASE_URL"])
print(u.set(database=sys.argv[1]).render_as_string(hide_password=False))
PY
)"
assert_alembic_target "$clone_url" "$clone_db"
(cd "$BACKEND_DIR" && DATABASE_URL="$clone_url" "$PYTHON_BIN" -m alembic upgrade "$TARGET_REVISION")
clone_revision="$(run_psql "$clone_db" "SELECT version_num FROM alembic_version;")"
[[ "$clone_revision" == "$TARGET_REVISION" ]] || fail "clone revision is ${clone_revision}"
clone_after="$(inventory_totals "$clone_db")"
# A structural backfill may legitimately add balance rows/quantities. Movement
# aggregates and authoritative product stock must remain byte-for-byte stable.
before_nonbalance="$(printf '%s' "$clone_before" | awk -F'|' '{ print $4 "|" $5 "|" $6 }')"
after_nonbalance="$(printf '%s' "$clone_after" | awk -F'|' '{ print $4 "|" $5 "|" $6 }')"
[[ "$after_nonbalance" == "$before_nonbalance" ]] || fail "movement or product-stock aggregates changed during migration"

# Reuse the strictly read-only classifier to reject Class B/C rows, affected
# or newly introduced duplicates, and failed stock reconciliation.
if ! analysis_output="$("$INVENTORY_ANALYSIS_SCRIPT" "$clone_db" 2>&1)"; then
  echo "Inventory analysis failed:" >&2
  echo "$analysis_output" >&2
  fail "inventory backfill classification is unsafe"
fi
if ! grep -Eq '^CONCLUSION: SAFE EXPECTED BACKFILL( WITH PRE-EXISTING DATA WARNING)?$' <<< "$analysis_output"; then
  echo "Inventory analysis conclusion:" >&2
  echo "$analysis_output" >&2
  fail "inventory backfill classification did not reconcile safely"
fi

echo "Creating fresh database: ${fresh_db}"
assert_temp_name "$fresh_db"
if db_exists_exact "$fresh_db"; then
  fail "fresh database name already exists: ${fresh_db}"
fi
sudo -u postgres createdb --owner="$db_user" "$fresh_db"
db_exists_exact "$fresh_db" || fail "fresh database was not created exactly"
provision_extensions "$fresh_db"
fresh_url="$(APEX_ENV_FILE="$ENV_FILE" "$PYTHON_BIN" - "$fresh_db" <<'PY'
import sys
import os
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
u = make_url(dotenv_values(os.environ["APEX_ENV_FILE"])["DATABASE_URL"])
print(u.set(database=sys.argv[1]).render_as_string(hide_password=False))
PY
)"
assert_alembic_target "$fresh_url" "$fresh_db"
(cd "$BACKEND_DIR" && DATABASE_URL="$fresh_url" "$PYTHON_BIN" -m alembic upgrade "$TARGET_REVISION")
fresh_revision="$(run_psql "$fresh_db" "SELECT version_num FROM alembic_version;")"
[[ "$fresh_revision" == "$TARGET_REVISION" ]] || fail "fresh database revision is ${fresh_revision}"

# Existing tests are run against the clone URL. They are aggregate/unit-safe
# and do not write production; integration tests may use the clone only.
test_log="$(mktemp "/tmp/${TEMP_PREFIX}tests_XXXXXX.log")"
chmod 600 "$test_log"
(cd "$BACKEND_DIR" && DATABASE_URL="$clone_url" "$PYTHON_BIN" -m unittest discover -s tests -q >"$test_log" 2>&1)
rm -f -- "$test_log"

echo "Clone revision: ${clone_revision}; fresh revision: ${fresh_revision}"
echo "Clone aggregate inventory totals after migration: ${clone_after}"
echo "PASS: Phase 1 staging validation completed"
success=1
