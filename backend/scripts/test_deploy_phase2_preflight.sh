#!/usr/bin/env bash
set -Eeuo pipefail

readonly REPO_DIR="/root/apexretail-pos"
readonly DEPLOY_SCRIPT="${REPO_DIR}/backend/scripts/deploy_phase2_production.sh"
readonly APPROVED_APK="${REPO_DIR}/backups/phase2-release/b7e80d1c9adf2d31ee3180b66035c016a1352c1b/apexretail-pos-phase2-final-v1.2.0-build4-b7e80d1.apk"

temporary_dir="$(mktemp -d /tmp/apex-phase2-preflight-test.XXXXXX)"
chmod 700 "$temporary_dir"
trap 'rm -rf -- "$temporary_dir"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

assert_required_entries() {
  local listing="$1"
  grep -Fxq 'assets/public/index.html' "$listing" || return 1
  grep -Eq '^assets/public/assets/index-.*\.js$' "$listing" || return 1
}

[[ -x "$DEPLOY_SCRIPT" ]] || fail "deployment script is missing"
[[ -f "$APPROVED_APK" ]] || fail "approved regression APK is missing"

# This is the production pattern: consume the producer completely before any
# early-exit matcher runs. A large listing makes SIGPIPE behavior reproducible
# if somebody regresses it to `producer | grep -q` under pipefail.
actual_listing="${temporary_dir}/actual-apk-entries.txt"
zipinfo -1 "$APPROVED_APK" >"$actual_listing"
chmod 600 "$actual_listing"
assert_required_entries "$actual_listing" || fail "approved APK entries were not recognized"

mock_listing="${temporary_dir}/mock-apk-entries.txt"
for number in $(seq 1 20000); do
  printf 'assets/mock/%05d.bin\n' "$number"
done >"$mock_listing"
printf '%s\n' 'assets/public/index.html' 'assets/public/assets/index-regression.js' >>"$mock_listing"
chmod 600 "$mock_listing"
assert_required_entries "$mock_listing" || fail "complete mocked listing was not recognized"

missing_listing="${temporary_dir}/missing-apk-entries.txt"
printf '%s\n' 'assets/public/assets/index-regression.js' >"$missing_listing"
chmod 600 "$missing_listing"
if assert_required_entries "$missing_listing"; then
  fail "missing index entry was accepted"
fi

# Reject the early-exit pipeline classes that are unsafe with pipefail.
if grep -En '\|[[:space:]]*(grep[[:space:]].*-q|head([[:space:]]|$)|awk[^|]*exit)' "$DEPLOY_SCRIPT" >"${temporary_dir}/unsafe-pipelines.txt"; then
  fail "deployment script contains an early-exit consumer pipeline"
fi

# Exercise a failure before confirmation or any production check. It must be
# nonzero and identify the exact-commit guard.
failure_output="${temporary_dir}/failure-output.txt"
set +e
"$DEPLOY_SCRIPT" \
  --commit 0000000000000000000000000000000000000000 \
  --apk /tmp/not-an-apk \
  --apk-sha256 0000000000000000000000000000000000000000000000000000000000000000 \
  --confirm-phase2-production >"$failure_output" 2>&1
failure_status=$?
set -e
[[ "$failure_status" -ne 0 ]] || fail "wrong-commit preflight unexpectedly succeeded"
grep -Fq 'does not equal approved commit' "$failure_output" || fail "wrong-commit failure was not explicit"
grep -Fq 'No automatic database restore or Alembic downgrade was attempted.' "$failure_output" || \
  fail "failure recovery policy was not reported"

echo "PASS: actual APK entries, pipefail regression, missing-entry rejection, pipeline audit, and fail-fast recovery path"
