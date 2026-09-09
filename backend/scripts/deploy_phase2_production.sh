#!/usr/bin/env bash
# Guarded Phase 2 production deployment. It never restores a database or runs
# an Alembic downgrade automatically. See rollback_phase2_production.md.
set -Eeuo pipefail

readonly REPO_DIR="/root/apexretail-pos"
readonly BACKEND_DIR="${REPO_DIR}/backend"
readonly POS_DIR="${REPO_DIR}/pos-web"
readonly BACKOFFICE_DIR="${REPO_DIR}/backoffice"
readonly PRODUCTION_DB="apexretail_pos"
readonly START_REVISION="c2phase1inventory"
readonly TARGET_REVISION="d3phase2discount"
readonly SERVICE_NAME="apexpos"
readonly BACKUP_ROOT="${REPO_DIR}/backups/phase2-production"
readonly POS_WEB_ROOT="/var/www/apexretail-pos"
readonly BACKOFFICE_WEB_ROOT="/var/www/apexpos-backoffice"
readonly DOWNLOADS_DIR="${BACKOFFICE_WEB_ROOT}/downloads"
readonly BUILD3_APK="${DOWNLOADS_DIR}/apexretail-pos-v1.1.1-build3-afe7564-20260903T085127Z.apk"
readonly PHASE2_RC_APK="${DOWNLOADS_DIR}/apexretail-pos-phase2-rc-v1.2.0-build4-424b45e-20260909T093604Z.apk"
readonly PHASE2_RC_SHA256="b5933f473a53426245723cb81a1ae4a9a40292b4bcc97202368f79d6c3cfc0e1"
readonly EXPECTED_SIGNER_SHA256="bb0d2ca7de6baa73009a4694fd1de1946548dc432992ba6443943c54306deb74"
readonly RETAINED_STASH="4bf05469530c72b04d5db1342e2ffd55b5b7ec53"
readonly LOCAL_HEALTH_URL="http://127.0.0.1:8000/api/health"
readonly PUBLIC_HEALTH_URL="https://api.apexpos.cloud/api/health"
readonly PUBLIC_POS_URL="https://pos.apexpos.cloud/"
readonly PUBLIC_BACKOFFICE_URL="https://backoffice.apexpos.cloud/"
readonly APKSIGNER="/opt/android-sdk/build-tools/35.0.0/apksigner"
readonly AAPT="/opt/android-sdk/build-tools/35.0.0/aapt"
readonly DEPLOY_SHELL_PID="$BASHPID"

success=0
service_initially_active=0
service_was_stopped=0
backup_verified=0
backup_dir=""
database_backup=""
pos_asset_backup=""
backoffice_asset_backup=""
published_apk=""
public_temp=""

fail() { echo "FAIL: $*" >&2; exit 1; }

recovery_instructions() {
  local status=$?
  [[ "$BASHPID" -eq "$DEPLOY_SHELL_PID" ]] || return "$status"
  [[ "$success" -eq 1 ]] && return 0
  trap - ERR EXIT
  set +e
  echo >&2
  echo "PHASE 2 DEPLOYMENT STOPPED (exit ${status})." >&2
  echo "No automatic database restore or Alembic downgrade was attempted." >&2
  [[ -n "$backup_dir" ]] && echo "Retain evidence directory: ${backup_dir}" >&2
  if [[ "$backup_verified" -eq 1 ]]; then
    echo "Verified database backup: ${database_backup}" >&2
  elif [[ -n "$database_backup" ]]; then
    echo "Do not use unverified dump: ${database_backup}" >&2
  fi
  [[ -n "$pos_asset_backup" ]] && echo "POS asset backup: ${pos_asset_backup}" >&2
  [[ -n "$backoffice_asset_backup" ]] && echo "Backoffice asset backup: ${backoffice_asset_backup}" >&2
  [[ -n "$published_apk" ]] && echo "Retain published APK: ${published_apk}" >&2
  [[ -n "$public_temp" ]] && rm -f -- "$public_temp"
  if [[ "$service_initially_active" -eq 1 && "$service_was_stopped" -eq 1 ]]; then
    echo "Attempting service availability recovery only; database state is unchanged by recovery." >&2
    systemctl start "$SERVICE_NAME"
    if systemctl is-active --quiet "$SERVICE_NAME"; then
      echo "Service is active; verify local and public health manually." >&2
    else
      echo "SERVICE RECOVERY FAILED; operator action is required." >&2
    fi
  fi
  echo "Follow backend/scripts/rollback_phase2_production.md before any further mutation." >&2
  exit "$status"
}
trap recovery_instructions ERR EXIT

[[ "$EUID" -eq 0 ]] || fail "run as root"
[[ "$PWD" == "$REPO_DIR" ]] || fail "run from exactly ${REPO_DIR}"
[[ "$#" -eq 7 && "$1" == "--commit" && "$3" == "--apk" && \
   "$5" == "--apk-sha256" && "$7" == "--confirm-phase2-production" ]] || \
  fail "usage: $0 --commit <commit> --apk <absolute-path> --apk-sha256 <sha256> --confirm-phase2-production"
approved_commit="$2"
approved_apk="$4"
approved_apk_sha256="$6"
[[ "$approved_commit" =~ ^[0-9a-f]{40}$ ]] || fail "approved commit must be 40 lowercase hexadecimal characters"
[[ "$approved_apk_sha256" =~ ^[0-9a-f]{64}$ ]] || fail "approved APK SHA-256 is malformed"
actual_commit="$(git rev-parse HEAD)"
[[ "$actual_commit" == "$approved_commit" ]] || \
  fail "HEAD ${actual_commit} does not equal approved commit ${approved_commit}"
git diff --quiet || fail "tracked working tree changes are present"
git diff --cached --quiet || fail "staged changes are present"
[[ -z "$(git ls-files --others --exclude-standard)" ]] || fail "untracked files are present"

required_confirmation="DEPLOY ${TARGET_REVISION} FROM ${START_REVISION} AT ${approved_commit}"
read -r -p "Type '${required_confirmation}' to continue: " confirmation </dev/tty
[[ "$confirmation" == "$required_confirmation" ]] || fail "production confirmation did not match"
unset confirmation required_confirmation

for command in git flock systemctl psql pg_dump pg_restore pg_isready runuser curl rsync \
  npm sha256sum unzip zipinfo cmp find awk stat install chmod nginx df sed grep \
  mktemp sort xargs sleep; do
  command -v "$command" >/dev/null || fail "required command not found: ${command}"
done
[[ -x "$APKSIGNER" && -x "$AAPT" ]] || fail "Android verification tools are missing"
[[ -x "${BACKEND_DIR}/venv/bin/python" ]] || fail "backend virtualenv is missing"
[[ -d "$POS_WEB_ROOT" && -d "$BACKOFFICE_WEB_ROOT" && -d "$DOWNLOADS_DIR" ]] || \
  fail "one or more production web roots are missing"
[[ -f "$BUILD3_APK" ]] || fail "published v1.1.1 build 3 APK is missing"
[[ -f "$PHASE2_RC_APK" ]] || fail "Phase 2 release candidate is missing"
[[ "$(sha256sum "$PHASE2_RC_APK" | awk '{print $1}')" == "$PHASE2_RC_SHA256" ]] || \
  fail "Phase 2 release candidate checksum changed"
[[ "$(git rev-parse 'stash@{0}')" == "$RETAINED_STASH" ]] || fail "retained stash changed"
expected_apk="${REPO_DIR}/backups/phase2-release/${approved_commit}/apexretail-pos-phase2-final-v1.2.0-build4-${approved_commit:0:7}.apk"
[[ "$approved_apk" == "$expected_apk" ]] || fail "approved APK path does not match the guarded commit"
[[ -f "$approved_apk" && ! -L "$approved_apk" ]] || fail "approved APK is missing or is a symlink"
[[ "$(stat -c '%a' "$approved_apk")" == 600 ]] || fail "approved APK must be mode 600 before publication"
[[ "$(sha256sum "$approved_apk" | awk '{print $1}')" == "$approved_apk_sha256" ]] || \
  fail "approved APK checksum mismatch"

readonly DASHBOARD_TOKEN_FILE="${APEX_PHASE2_DASHBOARD_TOKEN_FILE:-}"
readonly DASHBOARD_COMPANY_ID="${APEX_PHASE2_DASHBOARD_COMPANY_ID:-}"
[[ -n "$DASHBOARD_TOKEN_FILE" && -f "$DASHBOARD_TOKEN_FILE" ]] || \
  fail "APEX_PHASE2_DASHBOARD_TOKEN_FILE must name a protected token file"
[[ "$(stat -c '%a' "$DASHBOARD_TOKEN_FILE")" == 600 ]] || fail "Dashboard token file must be mode 600"
[[ "$DASHBOARD_COMPANY_ID" =~ ^[0-9a-fA-F-]{36}$ ]] || fail "Dashboard company ID is missing or malformed"
IFS= read -r dashboard_token <"$DASHBOARD_TOKEN_FILE"
[[ -n "$dashboard_token" ]] || fail "Dashboard token file is empty"

exec 9>"/run/lock/apexretail-phase2-deploy.lock"
flock -n 9 || fail "another Phase 2 deployment is running"

run_psql() {
  local sql="$1"
  (cd /tmp && runuser -u postgres -- psql -X --no-psqlrc -v ON_ERROR_STOP=1 \
    -qAt --dbname="$PRODUCTION_DB" -c "$sql")
}

assert_database_target() {
  APEX_EXPECTED_DB="$PRODUCTION_DB" "${BACKEND_DIR}/venv/bin/python" - <<'PY'
import os
from dotenv import dotenv_values
from sqlalchemy.engine import make_url
url = make_url(dotenv_values('/root/apexretail-pos/backend/.env')['DATABASE_URL'])
if url.database != os.environ['APEX_EXPECTED_DB']:
    raise SystemExit('configured database is not the guarded production database')
PY
}

health_payload_ok() {
  HEALTH_BODY="$1" "${BACKEND_DIR}/venv/bin/python" - <<'PY'
import json, os
body = json.loads(os.environ['HEALTH_BODY'])
if body.get('ok') is not True or body.get('app') != 'ApexRetail POS':
    raise SystemExit('unexpected health payload')
PY
}

wait_for_health() {
  local url="$1" body deadline=$((SECONDS + 60))
  while (( SECONDS < deadline )); do
    body=""
    if body="$(curl --fail --silent --show-error --max-time 5 "$url" 2>/dev/null)" && \
       health_payload_ok "$body" 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

write_aggregates() {
  local destination="$1"
  (cd /tmp && runuser -u postgres -- psql -X --no-psqlrc -v ON_ERROR_STOP=1 \
    --csv --dbname="$PRODUCTION_DB" >"$destination" <<'SQL'
SELECT 'accounting' AS section,
  count(*) FILTER (WHERE original_sale_id IS NULL) AS original_sales,
  count(*) FILTER (WHERE original_sale_id IS NOT NULL) AS refunds,
  COALESCE(sum(total_amount) FILTER (WHERE original_sale_id IS NULL),0) AS gross_sales,
  COALESCE(-sum(total_amount) FILTER (WHERE original_sale_id IS NOT NULL),0) AS refund_value,
  COALESCE(sum(total_amount),0) AS net_sales
FROM sales
WHERE (original_sale_id IS NULL AND lower(status) IN ('completed','partially_refunded','refunded'))
   OR (original_sale_id IS NOT NULL AND lower(status)='refunded');
SELECT 'inventory' AS section,
  (SELECT count(*) FROM inventory_balances) AS balance_rows,
  (SELECT COALESCE(sum(quantity),0) FROM inventory_balances) AS balance_quantity,
  (SELECT count(*) FROM inventory_movements) AS movement_rows,
  (SELECT COALESCE(sum(quantity),0) FROM inventory_movements) AS movement_quantity,
  (SELECT count(*) FROM products WHERE deleted=false) AS product_rows,
  (SELECT COALESCE(sum(stock_qty),0) FROM products WHERE deleted=false) AS product_quantity,
  (SELECT COALESCE(sum(stock_qty*cost_price),0) FROM products WHERE deleted=false) AS inventory_cost,
  (SELECT COALESCE(sum(stock_qty*selling_price),0) FROM products WHERE deleted=false) AS inventory_retail;
WITH tx AS (
  SELECT * FROM sales WHERE
    (original_sale_id IS NULL AND lower(status) IN ('completed','partially_refunded','refunded')) OR
    (original_sale_id IS NOT NULL AND lower(status)='refunded')
), costs AS (
  SELECT sale_id, COALESCE(sum(line_cost),0) AS cost FROM sale_items GROUP BY sale_id
)
SELECT 'dashboard' AS section, company_id, shop_id,
  (created_at AT TIME ZONE 'Africa/Harare')::date AS reporting_date,
  COALESCE(sum(total_amount) FILTER (WHERE original_sale_id IS NULL),0) AS gross_sales,
  COALESCE(-sum(total_amount) FILTER (WHERE original_sale_id IS NOT NULL),0) AS refunds,
  COALESCE(sum(total_amount),0) AS net_sales,
  COALESCE(sum(cost),0) AS cost_of_sales,
  COALESCE(sum(total_amount),0)-COALESCE(sum(cost),0) AS gross_profit
FROM tx LEFT JOIN costs ON costs.sale_id=tx.id
GROUP BY company_id,shop_id,(created_at AT TIME ZONE 'Africa/Harare')::date
ORDER BY company_id,shop_id,reporting_date;
SQL
  )
  chmod 600 "$destination"
}

verify_apk() {
  local apk="$1" package_line signer file relative embedded_hash source_hash
  unzip -tqq "$apk"
  "$APKSIGNER" verify --verbose --print-certs "$apk" >"${backup_dir}/apk-signature.txt"
  grep -Fq 'Verified using v1 scheme (JAR signing): true' "${backup_dir}/apk-signature.txt"
  grep -Fq 'Verified using v2 scheme (APK Signature Scheme v2): true' "${backup_dir}/apk-signature.txt"
  signer="$($APKSIGNER verify --print-certs "$apk" 2>/dev/null | awk -F': ' '/certificate SHA-256 digest/{print $2;exit}')"
  [[ "$signer" == "$EXPECTED_SIGNER_SHA256" ]] || fail "APK signer does not match build 3"
  package_line="$($AAPT dump badging "$apk" | sed -n '1p')"
  [[ "$package_line" == *"name='cloud.apexpos.pos'"* && "$package_line" == *"versionCode='4'"* && \
     "$package_line" == *"versionName='1.2.0'"* ]] || fail "APK package/version metadata is incorrect"
  zipinfo -1 "$apk" | grep -q '^assets/public/index.html$' || fail "embedded POS index is missing"
  zipinfo -1 "$apk" | grep -q '^assets/public/assets/index-.*\.js$' || fail "embedded POS bundle is missing"
  while IFS= read -r file; do
    relative="${file#${POS_DIR}/dist/}"
    embedded_hash="$(unzip -p "$apk" "assets/public/${relative}" | sha256sum | awk '{print $1}')"
    source_hash="$(sha256sum "$file" | awk '{print $1}')"
    [[ "$embedded_hash" == "$source_hash" ]] || fail "embedded POS asset differs from exact-commit build: ${relative}"
  done < <(find "${POS_DIR}/dist" -type f | sort)
}

verify_public_file() {
  local url="$1" expected="$2"
  public_temp="$(mktemp /tmp/apex-phase2-public.XXXXXX)"
  curl --fail --location --silent --show-error --max-time 30 "$url" --output "$public_temp"
  [[ -s "$public_temp" ]]
  cmp --silent "$expected" "$public_temp"
  rm -f -- "$public_temp"
  public_temp=""
}

verify_public_dashboard() {
  local response_file="$1"
  curl --fail --silent --show-error --max-time 15 \
    -H "Authorization: Bearer ${dashboard_token}" \
    "${PUBLIC_HEALTH_URL%/health}/dashboard/summary-v2/${DASHBOARD_COMPANY_ID}?range_key=today" \
    --output "$response_file"
  chmod 600 "$response_file"
  DASHBOARD_RESPONSE="$response_file" DASHBOARD_COMPANY_ID="$DASHBOARD_COMPANY_ID" \
    "${BACKEND_DIR}/venv/bin/python" - <<'PY'
import json, os
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import psycopg2
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

body = json.load(open(os.environ['DASHBOARD_RESPONSE']))
if body.get('range_key') != 'today' or body.get('reporting_timezone') != 'Africa/Harare':
    raise SystemExit('Dashboard range/timezone mismatch')
metrics = body.get('metrics', {})
if set(metrics) != {'gross_sales','net_sales','cost_of_sales','gross_profit','discounts','refunds'}:
    raise SystemExit('Dashboard metric set mismatch')
tz = ZoneInfo('Africa/Harare')
day = datetime.now(tz).date()
start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz).astimezone(timezone.utc)
url = make_url(dotenv_values('/root/apexretail-pos/backend/.env')['DATABASE_URL'])
conn = psycopg2.connect(url.render_as_string(hide_password=False))
with conn, conn.cursor() as q:
    q.execute('''WITH tx AS (SELECT * FROM sales s WHERE s.company_id=%s AND s.created_at >= %s
      AND s.created_at < %s AND ((s.original_sale_id IS NULL AND lower(s.status) IN
      ('completed','partially_refunded','refunded')) OR
      (s.original_sale_id IS NOT NULL AND lower(s.status)='refunded'))),
      sales AS (SELECT COALESCE(sum(total_amount) FILTER(WHERE original_sale_id IS NULL),0) gross,
      COALESCE(-sum(total_amount) FILTER(WHERE original_sale_id IS NOT NULL),0) refunds,
      COALESCE(sum(discount_amount) FILTER(WHERE original_sale_id IS NULL),0) discounts,
      count(*) FILTER(WHERE original_sale_id IS NULL) originals,
      count(discount_amount) FILTER(WHERE original_sale_id IS NULL) known FROM tx),
      costs AS (SELECT COALESCE(sum(i.line_cost),0) cost FROM sale_items i JOIN tx ON tx.id=i.sale_id)
      SELECT gross,refunds,gross-refunds,cost,gross-refunds-cost,discounts,originals=known FROM sales,costs''',
      (os.environ['DASHBOARD_COMPANY_ID'], start, end))
    gross, refunds, net, cost, profit, discounts, known = q.fetchone()
expected = {'gross_sales':gross,'refunds':refunds,'net_sales':net,
            'cost_of_sales':cost,'gross_profit':profit}
for name, value in expected.items():
    metric = metrics[name]
    if not metric.get('available') or Decimal(str(metric.get('value'))) != Decimal(value).quantize(Decimal('.01')):
        raise SystemExit(f'Dashboard {name} mismatch')
discount_metric = metrics['discounts']
if bool(discount_metric.get('available')) != bool(known):
    raise SystemExit('Dashboard discount availability mismatch')
if known and Decimal(str(discount_metric.get('value'))) != Decimal(discounts).quantize(Decimal('.01')):
    raise SystemExit('Dashboard discounts mismatch')
PY
}

systemctl is-active --quiet postgresql || fail "PostgreSQL is not active"
(cd /tmp && pg_isready --quiet) || fail "PostgreSQL is not accepting connections"
systemctl is-active --quiet "$SERVICE_NAME" || fail "backend is not initially active"
service_initially_active=1
wait_for_health "$LOCAL_HEALTH_URL" || fail "initial local health failed"
wait_for_health "$PUBLIC_HEALTH_URL" || fail "initial public health failed"
nginx -t
assert_database_target
[[ "$(run_psql 'SELECT current_database();')" == "$PRODUCTION_DB" ]] || fail "database identity mismatch"
[[ "$(run_psql 'SELECT version_num FROM alembic_version;')" == "$START_REVISION" ]] || \
  fail "production is not at ${START_REVISION}"
grep -Fq 'revision = "d3phase2discount"' backend/migrations/versions/d3_phase2_sale_discount_snapshot.py
grep -Fq 'down_revision = "c2phase1inventory"' backend/migrations/versions/d3_phase2_sale_discount_snapshot.py

echo "Running pre-mutation tests and builds"
(cd "$BACKEND_DIR" && venv/bin/python -m unittest discover -s tests -q)
(cd "$POS_DIR" && npm run test:discounts && npm run build)
(cd "$BACKOFFICE_DIR" && npm run test:dashboard && npm run build)
apk_source="$approved_apk"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_ROOT}/${stamp}-${approved_commit}"
database_backup="${backup_dir}/${PRODUCTION_DB}_before_phase2.dump"
pos_asset_backup="${backup_dir}/pos-assets"
backoffice_asset_backup="${backup_dir}/backoffice-assets"
install -d -m 700 "$BACKUP_ROOT" "$backup_dir" "$pos_asset_backup" "$backoffice_asset_backup"
verify_apk "$apk_source"
build3_signer="$($APKSIGNER verify --print-certs "$BUILD3_APK" 2>/dev/null | awk -F': ' '/certificate SHA-256 digest/{print $2;exit}')"
[[ "$build3_signer" == "$EXPECTED_SIGNER_SHA256" ]] || fail "published build 3 signer changed"
sha256sum "$apk_source" >"${backup_dir}/final-apk.sha256"
chmod 600 "${backup_dir}/apk-signature.txt" "${backup_dir}/final-apk.sha256"

echo "Creating and verifying all backups before service stop"
database_size="$(run_psql 'SELECT pg_database_size(current_database());')"
available_bytes="$(df --output=avail -B1 "$BACKUP_ROOT" | awk 'NR==2{print $1}')"
[[ "$database_size" =~ ^[0-9]+$ && "$available_bytes" =~ ^[0-9]+$ ]]
(( available_bytes >= database_size + 1073741824 )) || fail "insufficient backup space"
(umask 077; cd /tmp; runuser -u postgres -- pg_dump --format=custom --no-owner "$PRODUCTION_DB" >"$database_backup")
[[ -s "$database_backup" && "$(stat -c '%a' "$database_backup")" == 600 ]]
(cd /tmp && runuser -u postgres -- pg_restore --list) <"$database_backup" >"${backup_dir}/database-toc.txt"
sha256sum "$database_backup" >"${backup_dir}/database.sha256"
backup_verified=1
rsync --archive --delete "${POS_WEB_ROOT}/" "${pos_asset_backup}/"
rsync --archive --delete --exclude='/downloads/***' "${BACKOFFICE_WEB_ROOT}/" "${backoffice_asset_backup}/"
[[ -z "$(rsync --archive --checksum --dry-run --itemize-changes "${POS_WEB_ROOT}/" "${pos_asset_backup}/")" ]]
[[ -z "$(rsync --archive --checksum --dry-run --itemize-changes --exclude='/downloads/***' "${BACKOFFICE_WEB_ROOT}/" "${backoffice_asset_backup}/")" ]]
find "$DOWNLOADS_DIR" -maxdepth 1 -type f -printf '%f\0' | sort -z | xargs -0 -r -I{} sha256sum "${DOWNLOADS_DIR}/{}" >"${backup_dir}/retained-downloads.sha256"
write_aggregates "${backup_dir}/aggregates-before.csv"
chmod 600 "${backup_dir}/database-toc.txt" "${backup_dir}/database.sha256" \
  "${backup_dir}/retained-downloads.sha256"

echo "Stopping backend only after verified backups and aggregate evidence"
service_was_stopped=1
systemctl stop "$SERVICE_NAME"
systemctl is-active --quiet "$SERVICE_NAME" && fail "backend did not stop"
[[ "$(run_psql 'SELECT version_num FROM alembic_version;')" == "$START_REVISION" ]] || fail "revision changed before migration"
write_aggregates "${backup_dir}/aggregates-quiesced-before.csv"

echo "Migrating only ${START_REVISION} -> ${TARGET_REVISION}"
(cd "$BACKEND_DIR" && venv/bin/python -m alembic upgrade "$TARGET_REVISION")
[[ "$(run_psql 'SELECT version_num FROM alembic_version;')" == "$TARGET_REVISION" ]] || fail "target revision was not reached"
[[ "$(run_psql "SELECT count(*) FROM sales WHERE discount_amount IS NOT NULL;")" == 0 ]] || \
  fail "historical discount snapshots were unexpectedly populated"
write_aggregates "${backup_dir}/aggregates-after.csv"
cmp --silent "${backup_dir}/aggregates-quiesced-before.csv" "${backup_dir}/aggregates-after.csv" || \
  fail "accounting, inventory, or Dashboard aggregates changed during migration"

echo "Restarting and health-checking backend before asset publication"
systemctl restart "$SERVICE_NAME"
wait_for_health "$LOCAL_HEALTH_URL" || fail "post-migration local health failed"
service_was_stopped=0
wait_for_health "$PUBLIC_HEALTH_URL" || fail "post-migration public health failed"

echo "Publishing versioned Phase 2 assets"
rsync --archive --delete --delay-updates --chmod=D755,F644 "${POS_DIR}/dist/" "${POS_WEB_ROOT}/"
rsync --archive --delete --delay-updates --chmod=D755,F644 --exclude='/downloads/***' \
  "${BACKOFFICE_DIR}/dist/" "${BACKOFFICE_WEB_ROOT}/"
chmod 755 "$POS_WEB_ROOT" "$BACKOFFICE_WEB_ROOT" "$DOWNLOADS_DIR"
apk_filename="apexretail-pos-phase2-v1.2.0-build4-${approved_commit:0:7}-${stamp}.apk"
published_apk="${DOWNLOADS_DIR}/${apk_filename}"
[[ ! -e "$published_apk" ]] || fail "final APK destination already exists"
install -m 0644 "$apk_source" "$published_apk"
sha256sum --check --status "${backup_dir}/retained-downloads.sha256" || \
  fail "a retained download changed during publication"

for root in "$POS_WEB_ROOT" "$BACKOFFICE_WEB_ROOT"; do
  [[ "$(stat -c '%a' "$root")" == 755 ]]
  [[ -z "$(find "$root" -path "$DOWNLOADS_DIR" -prune -o -type d ! -perm 0755 -print -quit)" ]]
  [[ -z "$(find "$root" -path "$DOWNLOADS_DIR" -prune -o -type f ! -perm 0644 -print -quit)" ]]
done
[[ "$(stat -c '%a' "$published_apk")" == 644 ]]
nginx -t
wait_for_health "$LOCAL_HEALTH_URL" || fail "final local health failed"
wait_for_health "$PUBLIC_HEALTH_URL" || fail "final public health failed"
verify_public_file "$PUBLIC_POS_URL" "${POS_WEB_ROOT}/index.html"
verify_public_file "$PUBLIC_BACKOFFICE_URL" "${BACKOFFICE_WEB_ROOT}/index.html"
apk_url="${PUBLIC_BACKOFFICE_URL}downloads/${apk_filename}"
verify_public_file "$apk_url" "$published_apk"
verify_public_dashboard "${backup_dir}/dashboard-public-after.json"

success=1
trap - ERR EXIT
unset dashboard_token
echo "PASS: Phase 2 production deployment completed at ${approved_commit}"
echo "Database revision: ${TARGET_REVISION}"
echo "Evidence: ${backup_dir}"
echo "APK URL: ${apk_url}"
echo "APK SHA-256: $(sha256sum "$published_apk" | awk '{print $1}')"
