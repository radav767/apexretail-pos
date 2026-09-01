#!/usr/bin/env bash
# Guarded Phase 1 production deployment. This script intentionally performs no
# automatic database restore or Alembic downgrade on failure.
set -Eeuo pipefail
umask 077

readonly REPO_DIR="/root/apexretail-pos"
readonly BACKEND_DIR="${REPO_DIR}/backend"
readonly POS_DIR="${REPO_DIR}/pos-web"
readonly BACKOFFICE_DIR="${REPO_DIR}/backoffice"
readonly PRODUCTION_DB="apexretail_pos"
readonly START_REVISION="b8e51d8f4a21"
readonly TARGET_REVISION="c2phase1inventory"
readonly SERVICE_NAME="apexpos"
readonly BACKUP_DIR="${REPO_DIR}/backups/phase1-production"
readonly RESUME_BACKUP_FILE="${BACKUP_DIR}/apexretail_pos_before_phase1_20260901T083210Z.dump"
readonly POS_WEB_ROOT="/var/www/apexretail-pos"
readonly BACKOFFICE_WEB_ROOT="/var/www/apexpos-backoffice"
readonly DOWNLOADS_DIR="${BACKOFFICE_WEB_ROOT}/downloads"
readonly LOCAL_HEALTH_URL="http://127.0.0.1:8000/api/health"
readonly PUBLIC_HEALTH_URL="https://api.apexpos.cloud/api/health"
readonly PUBLIC_POS_URL="https://pos.apexpos.cloud/"
readonly PUBLIC_BACKOFFICE_URL="https://backoffice.apexpos.cloud/"
readonly DEPLOY_SHELL_PID="$BASHPID"

success=0
service_initially_active=0
backend_recovery_required=0
backup_file=""
backup_verified=0
backup_preflight_file=""
evidence_file=""
pos_asset_backup=""
backoffice_asset_backup=""
published_apk=""

fail() { echo "FAIL: $*" >&2; exit 1; }

recovery_instructions() {
  local status=$?
  # ERR is inherited by functions and command substitutions under errtrace.
  # Let only the top-level shell perform recovery and reporting.
  [[ "$BASHPID" -eq "$DEPLOY_SHELL_PID" ]] || return "$status"
  [[ "$success" -eq 1 ]] && return 0
  trap - ERR EXIT
  set +e
  echo >&2
  echo "DEPLOYMENT STOPPED (exit ${status}). No automatic restore or downgrade was attempted." >&2
  if [[ "$backup_verified" -eq 1 ]]; then
    echo "Verified database backup: ${backup_file}" >&2
  elif [[ -n "$backup_file" ]]; then
    echo "Database dump is not verified and must not be used: ${backup_file} (it may be failed, partial, empty, or nonexistent)" >&2
  fi
  [[ -n "$evidence_file" ]] && echo "Inventory evidence: ${evidence_file}" >&2
  [[ -n "$pos_asset_backup" ]] && echo "POS asset backup: ${pos_asset_backup}" >&2
  [[ -n "$backoffice_asset_backup" ]] && echo "Backoffice asset backup: ${backoffice_asset_backup}" >&2
  [[ -n "$published_apk" ]] && echo "Published APK (do not overwrite the prior APK): ${published_apk}" >&2
  if [[ -n "$backup_preflight_file" ]]; then
    rm -f -- "$backup_preflight_file"
  fi
  if [[ "$service_initially_active" -eq 1 && "$backend_recovery_required" -eq 1 ]]; then
    echo "Recovery: attempting to restart the initially active ${SERVICE_NAME} backend." >&2
    if systemctl start "$SERVICE_NAME"; then
      if wait_for_backend_health "$LOCAL_HEALTH_URL"; then
        echo "Recovery succeeded: ${SERVICE_NAME} is active and local health passed." >&2
      else
        echo "RECOVERY FAILED: ${SERVICE_NAME} did not become active and locally healthy; operator attention is required." >&2
      fi
    else
      echo "RECOVERY FAILED: systemctl could not start ${SERVICE_NAME}; operator attention is required." >&2
    fi
  fi
  echo "Follow backend/scripts/rollback_phase1_production.md. Do not restore the backup or run alembic downgrade without an approved recovery decision." >&2
  exit "$status"
}
trap recovery_instructions ERR EXIT

[[ "$EUID" -eq 0 ]] || fail "run this deployment as root"
[[ "$PWD" == "$REPO_DIR" ]] || fail "run from exactly ${REPO_DIR}"
[[ "$#" -eq 1 ]] || fail "usage: $0 {--confirm-phase1-production|--resume-phase1-assets}"
case "$1" in
  --confirm-phase1-production)
    deployment_mode="full"
    required_confirmation="DEPLOY ${TARGET_REVISION} TO ${PRODUCTION_DB}"
    ;;
  --resume-phase1-assets)
    deployment_mode="resume-assets"
    required_confirmation="RESUME PHASE1 ASSETS AT ${TARGET_REVISION}"
    ;;
  *)
    fail "usage: $0 {--confirm-phase1-production|--resume-phase1-assets}"
    ;;
esac

read -r -p "Type '${required_confirmation}' to continue: " confirmation </dev/tty
[[ "$confirmation" == "$required_confirmation" ]] || fail "production confirmation did not match"
unset confirmation
unset required_confirmation

for command in sudo psql pg_dump pg_restore pg_isready systemctl curl rsync npm npx git flock \
  sha256sum keytool unzip nginx cmp comm find awk stat wc install grep df sleep; do
  command -v "$command" >/dev/null || fail "required command not found: ${command}"
done
[[ -x "${BACKEND_DIR}/venv/bin/python" ]] || fail "backend virtualenv Python is missing"
[[ -x "${POS_DIR}/android/gradlew" ]] || fail "Android Gradle wrapper is missing"
[[ -d "$POS_WEB_ROOT" ]] || fail "POS web root is missing: ${POS_WEB_ROOT}"
[[ -d "$BACKOFFICE_WEB_ROOT" ]] || fail "Backoffice web root is missing: ${BACKOFFICE_WEB_ROOT}"
[[ -d "$DOWNLOADS_DIR" ]] || fail "protected APK downloads directory is missing: ${DOWNLOADS_DIR}"

# A clean commit makes application rollback and audit possible. Secrets and
# host backups must never be swept into a production deployment accidentally.
git diff --quiet || fail "tracked working tree changes are present; review and commit the deployment package first"
git diff --cached --quiet || fail "staged but uncommitted changes are present"
[[ -z "$(git ls-files --others --exclude-standard)" ]] || fail "untracked files are present; review them before deployment"

required_files=(
  "backend/migrations/versions/c1_phase1_refunds_sessions_audit.py"
  "backend/migrations/versions/c2_phase1_inventory_backfill_compat.py"
  "backend/app/auth/dependencies.py"
  "backend/app/models/audit_event.py"
  "backend/app/models/pos_session.py"
  "backend/tests/test_phase1_devices_and_sales.py"
  "backend/tests/test_phase1_refund_and_session_rules.py"
  "backend/tests/test_weighted_sales_and_subscriptions.py"
  "backend/scripts/validate_phase1_staging.sh"
  "backend/scripts/analyze_phase1_inventory_delta.sh"
  "pos-web/tests/entitlement.test.ts"
  "pos-web/scripts/build-production.mjs"
  "backoffice/src/pages/ProductsPage.tsx"
  "backoffice/src/pages/ShopsDevicesPage.tsx"
)
for required_file in "${required_files[@]}"; do
  [[ -f "${REPO_DIR}/${required_file}" ]] || fail "required Phase 1 file is missing: ${required_file}"
done
grep -Fq 'revision = "c1phase1refunds"' backend/migrations/versions/c1_phase1_refunds_sessions_audit.py || fail "c1 revision marker is missing"
grep -Fq 'down_revision = "b8e51d8f4a21"' backend/migrations/versions/c1_phase1_refunds_sessions_audit.py || fail "c1 parent revision is incorrect"
grep -Fq 'revision = "c2phase1inventory"' backend/migrations/versions/c2_phase1_inventory_backfill_compat.py || fail "c2 revision marker is missing"
grep -Fq 'down_revision = "c1phase1refunds"' backend/migrations/versions/c2_phase1_inventory_backfill_compat.py || fail "c2 parent revision is incorrect"
grep -Fq 'async def create_refund' backend/app/sales/service.py || fail "Phase 1 refund service is missing"
grep -Fq 'action="receipt_reprint"' backend/app/sales/service.py || fail "duplicate receipt audit behavior is missing"
grep -Fq 'action="product_archive"' backend/app/products/service.py || fail "product archive behavior is missing"
grep -Fq 'action="terminal_archive"' backend/app/devices/service.py || fail "terminal archive behavior is missing"
grep -Fq 'Take over this session' pos-web/src/App.tsx || fail "POS session takeover UI is missing"

exec 9>"/run/lock/apexretail-phase1-deploy.lock"
flock -n 9 || fail "another Phase 1 deployment is already running"

run_psql() {
  local database="$1" sql="$2"
  [[ "$database" == "$PRODUCTION_DB" ]] || fail "refusing PostgreSQL target other than ${PRODUCTION_DB}"
  (cd /tmp && sudo -u postgres psql -X --no-psqlrc -v ON_ERROR_STOP=1 -qAt --dbname="$database" -c "$sql")
}

assert_alembic_target() {
  APEX_EXPECTED_DB="$PRODUCTION_DB" "${BACKEND_DIR}/venv/bin/python" - <<'PY'
import os
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

url = make_url(dotenv_values("/root/apexretail-pos/backend/.env")["DATABASE_URL"])
if url.database != os.environ["APEX_EXPECTED_DB"]:
    raise SystemExit("configured Alembic database is not the guarded production database")
PY
}

health_payload_ok() {
  local body="$1"
  [[ -n "$body" ]] || return 1
  HEALTH_BODY="$body" "${BACKEND_DIR}/venv/bin/python" - <<'PY'
import json
import os

payload = json.loads(os.environ["HEALTH_BODY"])
if payload.get("ok") is not True:
    raise SystemExit("unexpected health payload")
PY
}

wait_for_backend_health() {
  local url="$1" body deadline
  deadline=$((SECONDS + 60))
  while (( SECONDS < deadline )); do
    body=""
    if systemctl is-active --quiet "$SERVICE_NAME" && \
       body="$(curl --fail --silent --max-time 1 "$url" 2>/dev/null)" && \
       [[ -n "$body" ]] && health_payload_ok "$body" 2>/dev/null; then
      return 0
    fi
    (( SECONDS < deadline )) && sleep 1
  done
  echo "Health check failed after 60 seconds: ${url}" >&2
  return 1
}

inventory_state() {
  run_psql "$PRODUCTION_DB" "
WITH candidate_sources AS (
  SELECT p.company_id, p.id AS product_id, p.stock_qty, p.reorder_level,
         p.cost_price, p.selling_price, b.id AS branch_id, b.shop_id
  FROM products p
  JOIN LATERAL (
    SELECT br.id, br.shop_id
    FROM branches br JOIN shops s ON s.id = br.shop_id
    WHERE br.company_id = p.company_id
      AND br.active = true AND br.deleted = false
      AND s.active = true AND s.deleted = false
    ORDER BY br.created_at LIMIT 1
  ) b ON true
  WHERE p.deleted = false
    AND NOT EXISTS (
      SELECT 1 FROM inventory_balances ib
      WHERE ib.company_id = p.company_id
        AND ib.branch_id = b.id AND ib.product_id = p.id
    )
)
SELECT
  (SELECT count(*) FROM inventory_balances),
  (SELECT COALESCE(sum(quantity), 0) FROM inventory_balances),
  (SELECT COALESCE(sum(ib.quantity * COALESCE(p.cost_price, 0)), 0)
     FROM inventory_balances ib LEFT JOIN products p ON p.id = ib.product_id),
  (SELECT count(*) FROM inventory_movements),
  (SELECT COALESCE(sum(quantity), 0) FROM inventory_movements),
  (SELECT COALESCE(sum(stock_qty), 0) FROM products WHERE deleted = false),
  (SELECT COALESCE(sum(stock_qty * COALESCE(cost_price, 0)), 0) FROM products WHERE deleted = false),
  (SELECT COALESCE(sum(stock_qty * COALESCE(selling_price, 0)), 0) FROM products WHERE deleted = false),
  (SELECT count(*) FROM candidate_sources),
  (SELECT COALESCE(sum(COALESCE(stock_qty, 0)), 0) FROM candidate_sources),
  (SELECT COALESCE(sum(COALESCE(stock_qty, 0) * COALESCE(cost_price, 0)), 0) FROM candidate_sources),
  (SELECT count(*) FROM candidate_sources cs
     WHERE EXISTS (SELECT 1 FROM inventory_balances ib WHERE ib.company_id = cs.company_id AND ib.product_id = cs.product_id)),
  (SELECT count(*) FROM (
     SELECT company_id, branch_id, product_id FROM inventory_balances
     GROUP BY company_id, branch_id, product_id HAVING count(*) > 1
   ) duplicates);"
}

write_class_a_candidates() {
  local destination="$1"
  run_psql "$PRODUCTION_DB" "
WITH candidate_sources AS (
  SELECT p.company_id, p.id AS product_id, COALESCE(p.stock_qty, 0) AS quantity,
         COALESCE(p.reorder_level, 0) AS reorder_level, b.id AS branch_id, b.shop_id
  FROM products p
  JOIN LATERAL (
    SELECT br.id, br.shop_id
    FROM branches br JOIN shops s ON s.id = br.shop_id
    WHERE br.company_id = p.company_id
      AND br.active = true AND br.deleted = false
      AND s.active = true AND s.deleted = false
    ORDER BY br.created_at LIMIT 1
  ) b ON true
  WHERE p.deleted = false
    AND NOT EXISTS (
      SELECT 1 FROM inventory_balances ib
      WHERE ib.company_id = p.company_id
        AND ib.branch_id = b.id AND ib.product_id = p.id
    )
)
SELECT company_id::text || '/' || branch_id::text || '/' || product_id::text,
       shop_id, quantity, reorder_level, true, false
FROM candidate_sources ORDER BY 1;" >"$destination"
  chmod 600 "$destination"
}

write_all_balances() {
  local destination="$1"
  run_psql "$PRODUCTION_DB" "
SELECT company_id::text || '/' || branch_id::text || '/' || product_id::text,
       shop_id, quantity, reorder_level, active, deleted
FROM inventory_balances ORDER BY 1;" >"$destination"
  chmod 600 "$destination"
}

systemctl is-active --quiet postgresql || fail "PostgreSQL is not active"
(cd /tmp && pg_isready --quiet) || fail "PostgreSQL is not accepting connections"
if systemctl is-active --quiet "$SERVICE_NAME"; then
  service_initially_active=1
else
  fail "${SERVICE_NAME} is not active"
fi
wait_for_backend_health "$LOCAL_HEALTH_URL" || fail "local backend health did not become ready"
wait_for_backend_health "$PUBLIC_HEALTH_URL" || fail "public backend health did not become ready"
nginx -t

database_identity="$(run_psql "$PRODUCTION_DB" 'SELECT current_database();')"
[[ "$database_identity" == "$PRODUCTION_DB" ]] || fail "production database identity mismatch"
assert_alembic_target

if [[ "$deployment_mode" == "resume-assets" ]]; then
  current_revision="$(run_psql "$PRODUCTION_DB" 'SELECT version_num FROM alembic_version;')"
  [[ "$current_revision" == "$TARGET_REVISION" ]] || \
    fail "resume requires production revision ${TARGET_REVISION}, found ${current_revision}"

  backup_file="$RESUME_BACKUP_FILE"
  [[ -f "$backup_file" ]] || fail "verified pre-migration backup does not exist: ${backup_file}"
  [[ -s "$backup_file" ]] || fail "verified pre-migration backup is empty: ${backup_file}"
  [[ "$(stat -c '%U:%G' "$backup_file")" == "root:root" ]] || fail "verified pre-migration backup ownership is not root:root"
  [[ "$(stat -c '%a' "$backup_file")" == 600 ]] || fail "verified pre-migration backup permissions are not 600"
  (cd /tmp && sudo -u postgres pg_restore --list) <"$backup_file" >/dev/null
  backup_verified=1
  echo "PASS: named pre-migration backup remains nonempty, mode 600, and valid"

  echo "Rebuilding final POS, Backoffice, Capacitor, and Android assets"
  (cd "$POS_DIR" && npm run build)
  (cd "$BACKOFFICE_DIR" && npm run build)
  (cd "$POS_DIR" && npx cap sync android)
  (cd "${POS_DIR}/android" && ./gradlew clean assembleDebug)

  apk_source="${POS_DIR}/android/app/build/outputs/apk/debug/app-debug.apk"
  [[ -s "$apk_source" ]] || fail "Android APK was not produced"
  unzip -tqq "$apk_source"
  keytool -printcert -jarfile "$apk_source" >/dev/null || fail "built APK is not signed"
  existing_apk="$(find "$DOWNLOADS_DIR" -maxdepth 1 -type f -name '*.apk' -print -quit)"
  if [[ -n "$existing_apk" ]]; then
    old_signer="$(keytool -printcert -jarfile "$existing_apk" 2>/dev/null | awk -F': ' '/SHA256:/{print $2; exit}')"
    new_signer="$(keytool -printcert -jarfile "$apk_source" 2>/dev/null | awk -F': ' '/SHA256:/{print $2; exit}')"
    [[ -n "$old_signer" && "$new_signer" == "$old_signer" ]] || fail "APK signer does not match the existing published APK"
  fi

  android_version_name="$(awk -F'"' '/versionName /{print $2; exit}' "${POS_DIR}/android/app/build.gradle")"
  android_version_code="$(awk '/versionCode /{print $2; exit}' "${POS_DIR}/android/app/build.gradle")"
  [[ "$android_version_code" == 2 ]] || fail "resume requires Android versionCode 2"
  [[ "$android_version_name" == "1.1.0" ]] || fail "resume requires Android versionName 1.1.0"

  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  install -d -m 700 -o root -g root "$BACKUP_DIR"
  pos_asset_backup="${BACKUP_DIR}/pos-assets-resume-${stamp}"
  backoffice_asset_backup="${BACKUP_DIR}/backoffice-assets-resume-${stamp}"
  install -d -m 700 "$pos_asset_backup" "$backoffice_asset_backup"
  rsync --archive --delete "${POS_WEB_ROOT}/" "${pos_asset_backup}/"
  rsync --archive --delete --exclude='/downloads/***' "${BACKOFFICE_WEB_ROOT}/" "${backoffice_asset_backup}/"

  echo "Publishing resumed POS and Backoffice web assets"
  rsync --archive --delete --delay-updates "${POS_DIR}/dist/" "${POS_WEB_ROOT}/"
  rsync --archive --delete --delay-updates --exclude='/downloads/***' \
    "${BACKOFFICE_DIR}/dist/" "${BACKOFFICE_WEB_ROOT}/"
  [[ -d "$DOWNLOADS_DIR" ]] || fail "Backoffice downloads directory was not preserved"

  apk_filename="apexretail-pos-phase1-v${android_version_name}-build${android_version_code}-${stamp}.apk"
  published_apk="${DOWNLOADS_DIR}/${apk_filename}"
  [[ ! -e "$published_apk" ]] || fail "versioned APK destination already exists"
  install -m 0644 "$apk_source" "$published_apk"

  curl --fail --silent --show-error --max-time 20 --output /dev/null "$PUBLIC_POS_URL"
  curl --fail --silent --show-error --max-time 20 --output /dev/null "$PUBLIC_BACKOFFICE_URL"
  apk_url="https://backoffice.apexpos.cloud/downloads/${apk_filename}"
  remote_apk="$(mktemp /tmp/apexretail-phase1-resume-apk.XXXXXX)"
  curl --fail --silent --show-error --max-time 180 --output "$remote_apk" "$apk_url"
  cmp --silent "$published_apk" "$remote_apk" || fail "public APK bytes do not match the published file"
  rm -f -- "$remote_apk"
  apk_sha256="$(sha256sum "$published_apk" | awk '{print $1}')"
  echo "APK URL: ${apk_url}"
  echo "APK SHA-256: ${apk_sha256}"

  wait_for_backend_health "$LOCAL_HEALTH_URL" || fail "final local backend health failed"
  wait_for_backend_health "$PUBLIC_HEALTH_URL" || fail "final public backend health failed"

  success=1
  trap - ERR EXIT
  echo "PASS: Phase 1 asset deployment resumed at ${TARGET_REVISION}"
  echo "Verified pre-migration backup: ${backup_file}"
  exit 0
fi

starting_revision="$(run_psql "$PRODUCTION_DB" 'SELECT version_num FROM alembic_version;')"
[[ "$starting_revision" == "$START_REVISION" ]] || fail "production revision is ${starting_revision}, expected ${START_REVISION}"

echo "Running all pre-mutation tests and production builds"
(cd "$BACKEND_DIR" && venv/bin/python -m unittest discover -s tests -q)
(cd "$POS_DIR" && npm run test:entitlement)
(cd "$POS_DIR" && npm run build)
(cd "$BACKOFFICE_DIR" && npm run build)
(cd "$POS_DIR" && npx cap sync android)
(cd "${POS_DIR}/android" && ./gradlew clean assembleDebug)

apk_source="${POS_DIR}/android/app/build/outputs/apk/debug/app-debug.apk"
[[ -s "$apk_source" ]] || fail "Android APK was not produced"
unzip -tqq "$apk_source"
keytool -printcert -jarfile "$apk_source" >/dev/null || fail "built APK is not signed"
existing_apk="$(find "$DOWNLOADS_DIR" -maxdepth 1 -type f -name '*.apk' -print -quit)"
if [[ -n "$existing_apk" ]]; then
  old_signer="$(keytool -printcert -jarfile "$existing_apk" 2>/dev/null | awk -F': ' '/SHA256:/{print $2; exit}')"
  new_signer="$(keytool -printcert -jarfile "$apk_source" 2>/dev/null | awk -F': ' '/SHA256:/{print $2; exit}')"
  [[ -n "$old_signer" && "$new_signer" == "$old_signer" ]] || fail "APK signer does not match the existing published APK"
fi

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 -o root -g root "$BACKUP_DIR"
backup_file="${BACKUP_DIR}/${PRODUCTION_DB}_before_phase1_${stamp}.dump"
evidence_file="${BACKUP_DIR}/inventory_before_phase1_${stamp}.txt"
candidate_file="${BACKUP_DIR}/class_a_candidates_${stamp}.txt"
post_balances_file="${BACKUP_DIR}/balances_after_phase1_${stamp}.txt"
matched_candidates_file="${BACKUP_DIR}/class_a_matched_${stamp}.txt"

backup_preflight_file="${BACKUP_DIR}/.phase1-backup-preflight-${stamp}"
printf '%s\n' "phase1-backup-preflight-${stamp}" >"$backup_preflight_file"
read -r backup_preflight_value <"$backup_preflight_file"
[[ "$backup_preflight_value" == "phase1-backup-preflight-${stamp}" ]] || fail "backup path preflight read did not match"
rm -f -- "$backup_preflight_file"
backup_preflight_file=""

database_size_bytes="$(run_psql "$PRODUCTION_DB" 'SELECT pg_database_size(current_database());')"
available_backup_bytes="$(df --output=avail -B1 "$BACKUP_DIR" | awk 'NR == 2 { print $1 }')"
[[ "$database_size_bytes" =~ ^[0-9]+$ ]] || fail "could not determine production database size"
[[ "$available_backup_bytes" =~ ^[0-9]+$ ]] || fail "could not determine backup filesystem free space"
required_backup_bytes=$((database_size_bytes + 1073741824))
(( available_backup_bytes >= required_backup_bytes )) || \
  fail "insufficient backup space: ${available_backup_bytes} bytes available, ${required_backup_bytes} required"
echo "PASS: backup path write/read/remove preflight and disk-space check succeeded"

echo "Stopping backend to prevent concurrent writes during backup and migration"
backend_recovery_required=1
systemctl stop "$SERVICE_NAME"
systemctl is-active --quiet "$SERVICE_NAME" && fail "${SERVICE_NAME} did not stop"

(cd /tmp && sudo -u postgres pg_dump --format=custom --no-owner "$PRODUCTION_DB") >"$backup_file"
[[ -s "$backup_file" ]] || fail "production backup is empty"
[[ "$(stat -c '%U:%G' "$backup_file")" == "root:root" ]] || fail "production backup ownership is not root:root"
[[ "$(stat -c '%a' "$backup_file")" == 600 ]] || fail "production backup permissions are not 600"
(cd /tmp && sudo -u postgres pg_restore --list) <"$backup_file" >/dev/null
backup_verified=1
echo "PASS: root-owned mode-600 database backup is nonempty and pg_restore validation succeeded"

before_state="$(inventory_state)"
printf '%s\n' "$before_state" >"$evidence_file"
chmod 600 "$evidence_file"
echo "Pre-deployment inventory aggregates (balance count|balance quantity|balance cost value|movement count|movement quantity|product quantity|product cost value|product retail value|Class A rows|Class A quantity|Class A cost value|unsafe candidate rows|duplicate keys):"
echo "$before_state"

IFS='|' read -r before_balance_count before_balance_qty before_balance_cost \
  before_movement_count before_movement_qty before_product_qty before_product_cost \
  before_product_retail class_a_count class_a_qty class_a_cost unsafe_candidates \
  before_duplicates <<<"$before_state"
[[ "$unsafe_candidates" == 0 ]] || fail "backfill contains non-Class-A rows with pre-existing product balances"
[[ "$before_duplicates" == 0 ]] || fail "duplicate (company, branch, product) balance keys exist before migration"
write_class_a_candidates "$candidate_file"
[[ "$(wc -l <"$candidate_file")" -eq "$class_a_count" ]] || fail "Class A evidence row count mismatch"

current_revision="$(run_psql "$PRODUCTION_DB" 'SELECT version_num FROM alembic_version;')"
[[ "$current_revision" == "$START_REVISION" ]] || fail "production revision changed before migration"

echo "Upgrading production only to ${TARGET_REVISION}"
(cd "$BACKEND_DIR" && venv/bin/python -m alembic upgrade "$TARGET_REVISION")
post_revision="$(run_psql "$PRODUCTION_DB" 'SELECT version_num FROM alembic_version;')"
[[ "$post_revision" == "$TARGET_REVISION" ]] || fail "post-migration revision is ${post_revision}, expected ${TARGET_REVISION}"

after_state="$(inventory_state)"
printf '%s\n' "$after_state" >>"$evidence_file"
IFS='|' read -r after_balance_count after_balance_qty after_balance_cost \
  after_movement_count after_movement_qty after_product_qty after_product_cost \
  after_product_retail remaining_candidates remaining_candidate_qty remaining_candidate_cost \
  after_unsafe_candidates after_duplicates <<<"$after_state"

STATE_VALUES="$before_state" AFTER_VALUES="$after_state" "${BACKEND_DIR}/venv/bin/python" - <<'PY'
import os
from decimal import Decimal

before = [Decimal(value) for value in os.environ["STATE_VALUES"].split("|")]
after = [Decimal(value) for value in os.environ["AFTER_VALUES"].split("|")]

checks = {
    "balance row count": after[0] == before[0] + before[8],
    "balance quantity": after[1] == before[1] + before[9],
    "balance cost value": after[2] == before[2] + before[10],
    "movement count": after[3] == before[3],
    "movement quantity": after[4] == before[4],
    "canonical product quantity": after[5] == before[5],
    "canonical product cost value": after[6] == before[6],
    "canonical product retail value": after[7] == before[7],
    "backfill idempotence": after[8] == 0,
    "post-migration duplicate keys": after[12] == 0,
}
failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise SystemExit("Class A reconciliation failed: " + ", ".join(failed))
PY

write_all_balances "$post_balances_file"
comm -12 "$candidate_file" "$post_balances_file" >"$matched_candidates_file"
chmod 600 "$post_balances_file" "$matched_candidates_file"
cmp --silent "$candidate_file" "$matched_candidates_file" || fail "one or more Class A rows do not match their authoritative source"
echo "PASS: Class A backfill reconciled; structural balance deltas match exactly and movement/product accounting values are invariant"

echo "Restarting backend and checking health"
systemctl restart "$SERVICE_NAME"
wait_for_backend_health "$LOCAL_HEALTH_URL" || fail "local backend health did not become ready after restart"
backend_recovery_required=0
wait_for_backend_health "$PUBLIC_HEALTH_URL" || fail "public backend health did not become ready after restart"

pos_asset_backup="${BACKUP_DIR}/pos-assets-${stamp}"
backoffice_asset_backup="${BACKUP_DIR}/backoffice-assets-${stamp}"
install -d -m 700 "$pos_asset_backup" "$backoffice_asset_backup"
rsync --archive --delete "${POS_WEB_ROOT}/" "${pos_asset_backup}/"
rsync --archive --delete --exclude='/downloads/***' "${BACKOFFICE_WEB_ROOT}/" "${backoffice_asset_backup}/"

echo "Publishing POS and Backoffice web assets"
rsync --archive --delete --delay-updates "${POS_DIR}/dist/" "${POS_WEB_ROOT}/"
# The downloads exclusion is mandatory: --delete must never remove retained APKs.
rsync --archive --delete --delay-updates --exclude='/downloads/***' \
  "${BACKOFFICE_DIR}/dist/" "${BACKOFFICE_WEB_ROOT}/"
[[ -d "$DOWNLOADS_DIR" ]] || fail "Backoffice downloads directory was not preserved"

android_version_name="$(awk -F'"' '/versionName /{print $2; exit}' "${POS_DIR}/android/app/build.gradle")"
android_version_code="$(awk '/versionCode /{print $2; exit}' "${POS_DIR}/android/app/build.gradle")"
[[ "$android_version_name" =~ ^[0-9]+([.][0-9]+)*$ ]] || fail "unsafe Android versionName"
[[ "$android_version_code" =~ ^[0-9]+$ ]] || fail "unsafe Android versionCode"
apk_filename="apexretail-pos-phase1-v${android_version_name}-build${android_version_code}-${stamp}.apk"
published_apk="${DOWNLOADS_DIR}/${apk_filename}"
[[ ! -e "$published_apk" ]] || fail "versioned APK destination already exists"
install -m 0644 "$apk_source" "$published_apk"

wait_for_backend_health "$PUBLIC_HEALTH_URL" || fail "final public backend health failed"
curl --fail --silent --show-error --max-time 20 --output /dev/null "$PUBLIC_POS_URL"
curl --fail --silent --show-error --max-time 20 --output /dev/null "$PUBLIC_BACKOFFICE_URL"
apk_url="https://backoffice.apexpos.cloud/downloads/${apk_filename}"
remote_apk="$(mktemp /tmp/apexretail-phase1-apk.XXXXXX)"
curl --fail --silent --show-error --max-time 180 --output "$remote_apk" "$apk_url"
cmp --silent "$published_apk" "$remote_apk" || fail "public APK bytes do not match the published file"
rm -f -- "$remote_apk"
apk_sha256="$(sha256sum "$published_apk" | awk '{print $1}')"
echo "APK URL: ${apk_url}"
echo "APK SHA-256: ${apk_sha256}"

echo
echo "Required manual smoke checks (use approved disposable QA fixtures; create no real payment):"
echo "  1. Log in to Backoffice and POS with approved smoke-test accounts."
echo "  2. Confirm shop and terminal selection, including the no-terminal state."
echo "  3. Confirm session takeover signs out the prior device."
echo "  4. Reprint an approved test receipt and confirm DUPLICATE marking/count."
echo "  5. Refund only an approved non-financial test receipt and verify stock/audit behavior."
echo "  6. Create/archive a disposable QA product and confirm it remains auditable."
echo "  7. Create/archive a disposable QA terminal and confirm it cannot be selected."
echo "  8. Do not initiate or repeatedly test Paynow checkout; its network case remains pending with Paynow."
read -r -p "After completing all checks, type 'PHASE1 SMOKE PASSED': " smoke_confirmation </dev/tty
[[ "$smoke_confirmation" == "PHASE1 SMOKE PASSED" ]] || fail "manual smoke checks were not confirmed"
unset smoke_confirmation

success=1
trap - ERR EXIT
echo "PASS: Phase 1 production deployment completed at ${TARGET_REVISION}"
echo "Retained database backup: ${backup_file}"
echo "Retained deployment evidence: ${evidence_file}"
