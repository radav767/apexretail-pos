#!/usr/bin/env bash
set -Eeuo pipefail

repo="$(git rev-parse --show-toplevel)"
commit="$(git rev-parse HEAD)"
validator="$repo/backend/scripts/validate_dashboard_phase3.sh"
temporary_parent="$(mktemp -d /tmp/apex-phase3-detached-regression-XXXXXX)"
worktree="$temporary_parent/worktree"

cleanup() {
  local status=$?
  trap - EXIT
  if [[ -d "$worktree" ]]; then
    git -C "$repo" worktree remove --force "$worktree" >/dev/null 2>&1 || status=1
  fi
  rm -rf -- "$temporary_parent"
  exit "$status"
}
trap cleanup EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

git -C "$repo" diff --quiet || fail "tracked changes must be committed before detached regression"
git -C "$repo" diff --cached --quiet || fail "staged changes must be committed before detached regression"
git -C "$repo" worktree add --detach "$worktree" "$commit" >/dev/null
[[ ! -e "$worktree/backend/.env" ]] || fail "detached regression unexpectedly contains backend/.env"
ln -s "$repo/backend/venv" "$worktree/backend/venv"

success_log="$temporary_parent/detached-success.log"
(cd "$worktree" && \
  DATABASE_URL='postgresql+asyncpg://ignored@/apexretail_pos?host=/var/run/postgresql' \
  APP_ENV=production JWT_SECRET=must-not-be-used \
  bash backend/scripts/validate_dashboard_phase3.sh) >"$success_log" 2>&1
grep -Fq 'PASS: isolated database identity verified before migrations' "$success_log" || \
  fail "detached staging did not verify its isolated database"
grep -Fq 'Ran 112 tests' "$success_log" || fail "detached staging did not run the complete backend suite"
grep -Fq 'threshold_passed": true' "$success_log" || fail "detached staging missed the performance gate"
grep -Fq 'PASS: temporary PostgreSQL stopped; no PID or socket remains' "$success_log" || \
  fail "detached staging cleanup was not verified"

unavailable_socket="/tmp/apex-phase3-validation-unavailable-$RANDOM-$RANDOM"
failure_log="$temporary_parent/detached-unavailable.log"
set +e
(cd "$worktree" && \
  DATABASE_URL='postgresql+asyncpg://ignored@/apexretail_pos?host=/var/run/postgresql' \
  APP_ENV=production JWT_SECRET=must-not-be-used \
  PHASE3_EXISTING_TEST_SOCKET="$unavailable_socket" \
  PHASE3_EXISTING_TEST_DATABASE=apexretail_phase2_test_unavailable \
  bash backend/scripts/validate_dashboard_phase3.sh) >"$failure_log" 2>&1
failure_status=$?
set -e
[[ "$failure_status" -ne 0 ]] || fail "unavailable isolated database unexpectedly passed"
grep -Fq 'FAIL: isolated PostgreSQL is unavailable before migrations' "$failure_log" || \
  fail "unavailable isolated database failure was not explicit"
if grep -Fq 'Running upgrade' "$failure_log"; then
  fail "migration ran after the isolated database availability check failed"
fi
[[ ! -e "$unavailable_socket" ]] || fail "unavailable test created an unexpected socket path"

echo "PASS: detached staging works without .env and unavailable isolation fails before migrations"
