# Limited release preparation and independent rehearsal — 27 November 2026 UTC

Base/operator-pushed061051afb765c5aeb27f50d4e734ebf6721ee6da. New user instruction authorizes limited POS/BO deployment only after critical gates; no production deployment performed. Scope/finite gate ledger: docs/PHASE11-LIMITED-RELEASE.md; original audit-row inventory: docs/PHASE11-ACCEPTANCE-INVENTORY.md. Super Admin stays closed. Test executions do not close programme requirements.

## Isolation and provenance

New root `/tmp/apex-phase11-independent-release-5lrb0b7l`, new archive `git archive HEAD` (SHA in rehearsed-source.json), fresh Python3.10 venv, new PostgreSQL14 private cluster `/tmp/apex-phase11-release-pg-ysjagwtm`, port55443, listen_addresses empty, no TCP. Separate from retained previous fixtures. New databases named in run_rehearsal.py/postgres.json; test name reused only in this **different cluster**. All generic commands env-i, synthetic JWT, no inherited production settings/provider credentials. Test fixture chain inspected: Phase11→Phase7D→printing, explicit disposable DB whitelist, outer transaction/savepoints. Browser sinks/blocked origins; no printer/provider sends.

Initial local cached wheel install lacked PyJWT. Public pinned download initially failed sandbox DNS; approved network retry succeeded with no production pip config:

```
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PIP_CONFIG_FILE=/dev/null /tmp/apex-phase11-independent-release-5lrb0b7l/venv/bin/python -m pip download --disable-pip-version-check --retries 1 --timeout 15 --index-url https://pypi.org/simple --dest /tmp/apex-phase11-independent-release-5lrb0b7l/wheelhouse -r /tmp/apex-phase11-independent-release-5lrb0b7l/source/backend/requirements-document-tests.lock -r /tmp/apex-phase11-independent-release-5lrb0b7l/source/backend/requirements-test.lock
```

Fresh offline `pip install --no-index --find-links <root>/wheelhouse -r <root>/source/backend/requirements-document-tests.lock -r <root>/source/backend/requirements-test.lock` passes; pip check passes.57 wheel files/hashes retained in wheelhouse.json, including cached/downloaded versions/tags, not57 distinct requirements. No vulnerability/advisory certification claimed.

Owned nonsymlink node_modules copied from previous isolated builds, not clean npm installation; shared symlink untouched/no npm ci. Node20.20.2/npm10.8.2. Builds in `<root>/source/{pos-web,backoffice}`:

```
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp VITE_API_BASE_URL=/api VITE_BACKOFFICE_URL=https://backoffice.synthetic.invalid ENTITLEMENT_PUBLIC_KEYRING_FILE=/tmp/apex-phase11-shell-keyring.json npm run build
```

Both pass, known chunk-size warning. Retained build logs trim line-ending whitespace only. Initial BO build ran before dependency copy completed (tsc absent); after completion rerun passes. Later recovery-availability overlay copied from exact listed source hashes and BO rebuilt successfully. A misplaced root build/initial pytest without backend cwd failed before execution; corrected commands pass. These are synthetic-origin/keyring builds, **not final deployable artifacts**. Source overlay breaks an all-061051a claim deliberately; exact overlay hashes are explicit and final candidate freeze remains open.

## Migration / restore

New cluster `initdb -A trust --no-locale -E UTF8` under postgres and private700 directory; pg_ctl socket-only55443. Fresh DB `apex_phase11_release_fresh` upgraded head (79 revisions). Upgrade DB initialized `alembic upgrade p10a_platform_management` then synthetic seed. Every Alembic command uses env-i APP_ENV=test/synthetic JWT and exact URL `postgresql+asyncpg://postgres@/<named-db>?host=/tmp/apex-phase11-release-pg-ysjagwtm&port=55443`.

```
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp /tmp/apex-phase11-independent-release-5lrb0b7l/venv/bin/python artifacts/phase11-limited-release-20261127/isolated_rehearsal.py seed --root /tmp/apex-phase11-independent-release-5lrb0b7l --database apex_phase11_release_upgrade
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp /tmp/apex-phase11-independent-release-5lrb0b7l/venv/bin/python artifacts/phase11-limited-release-20261127/run_rehearsal.py
```

All driver steps pass. p10a→p11ac29 additive steps;78 original non-version tables/7 seeded rows' original columns unchanged. Seed includes company/user/shop/branch/product(stock98)/cash sale25/tender30/change5/item; **not a complete stock/credit/offline migration corpus**. pg_dump custom and pg_restore --exit-on-error into separately created empty restore DB;96 non-version tables/7 rows match all column hashes. Original upgrade DB then receives a newer synthetic sale and user.session_version7; head upgrade no-op retains96 tables/8 rows. This is DB preservation evidence, **not an interrupted deployment/forward repair test**, production backup, off-host encryption/custody or independent human witness. No downgrade or old restore over newer rows. Synthetic dump retained only in /tmp, hash recorded. Driver is single-use for empty fixtures, not a production tool.

## API/security/replay tests

From `<root>/source/backend`, env-i PATH/HOME, APP_ENV=test, JWT_SECRET=synthetic-independent-release-secret-not-production-20261127, DATABASE_URL and APEX_PHASE7D_TEST_DATABASE_URL both `postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-release-pg-ysjagwtm&port=55443`:

```
<root>/venv/bin/python -m pytest -q tests/test_phase11_user_sessions.py tests/test_phase11_remembered_sessions.py tests/test_phase11_identity_boundaries.py tests/test_phase11_sale_replay.py tests/test_phase11_stock_replay.py tests/test_phase11_financial_replay.py tests/test_phase11_procurement.py tests/test_phase11_durable_counts.py tests/test_phase11_reconciliation_exports.py
```

59 pass,29 subtests, no skips, existing Pydantic deprecation warnings. Tests use test environment; not final production-config certification. New candidate `tests/test_phase11_auth_capabilities.py` run from repo/backend with same env-i/synthetic JWT and unreachable DATABASE_URL `postgresql+asyncpg://synthetic:synthetic@127.0.0.1:1/synthetic_unreachable`:1 pass/3 subtests (production disabled/test disabled/test sink). No DB. Route returns only deployment availability/no-store, not account information. Generic reset endpoint/session revocation semantics unchanged.

Node env-i in archive POS: `node scripts/run-auth-lifecycle-tests.mjs`8pass, `run-offline-lease-tests.mjs`11pass, `run-entitlement-tests.mjs`7pass, no skips. New policy inventory requires exact unreachable DB name `phase11_unreachable` (first wrong-name attempts safely refused); generated300 routes/170 mutating/27 visible billable dependencies, static assessment only.

## Real shell and persistence

Owned synthetic API Uvicorn loopback18131, cwd `<root>/source/backend`, env-i APP_ENV=test/JWT as above, DATABASE_URL shell DB on55443, BACKOFFICE_ORIGIN=https://backoffice.synthetic.invalid, ENTITLEMENT_SIGNING_KEY_FILE=/tmp/apex-phase11-shell-key.pem, ENTITLEMENT_PUBLIC_KEYRING_FILE=/tmp/apex-phase11-shell-keyring.json, ENTITLEMENT_ACTIVE_KEY_ID=phase11-shell-synthetic, PRODUCT_IMAGE_ROOT inside newroot. Split/quotation/email/delivery flags **unset, default disabled**. Initial synthetic key ID corrected before any shell run. No production API process affected.

```
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp node artifacts/phase11-limited-release-20261127/daily-shell.mjs
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp node artifacts/phase11-limited-release-20261127/capabilities-shell.mjs
```

Daily real first-party owner/restricted login/PIN/open shift, POS minimal menu/stock/history/receipt, BO hub/original pages/deep links/back, committed transfer/count exact UUID/payload recovery, restricted refund/report/BO denial, wrong-company handoff denial and actual owner reauthentication/one-use handoff pass. Cashier identity and original receipt JSON unchanged.390px/28px root reflow; zero page errors/unexpected origins. Recovery shell verifies real disabled metadata and downlevel404 both show unavailable email recovery, no forgot request. Initial test root-route path assertion corrected; final pass. Browser only Chromium/headless-shell1243; no Firefox/WebKit/native AT/physical print/device acceptance.

Independent `persistence.py` env-i PYTHONPATH=<root>/source/backend, APP_ENV=test/JWT synthetic, DATABASE_URL shell private55443, interpreter newvenv: verified read-only transaction; source96/destination2, one transfer out/in/count, original sale1/refund0; original movement ownership reconciles. Refund/credit/FX whole-shell acceptance is **not** established by this journey.

## Production preflight — metadata/config only

Approved `env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp <root>/venv/bin/python artifacts/phase11-limited-release-20261127/production_preflight.py` yields sanitized production-preflight.json. Metadata-only DB repeatable-read read-only asserted **before** queries, no business rows. Installed schema p10a, tables79/triggers24, PostgreSQL14.24; actual runtime194 application files/manifest+runtime lock hashes. Service cwd original backend but ExecStart --app-dir imports /opt runtime; UID0. Candidate Settings validates with existing production values, no secret validation inputs output; optional four modes disabled. **Effective systemd credential signer matches active public ring key**, deadline valid. Deprecated inline pair matches itself but differs from ring: inactive inline comparison is not a runtime key mismatch. No key/credential changes. Existing public-input file elsewhere has a different hash and must not be used silently as current ring.

Admin holding503 retained; no production service/nginx/schema writes. Installed backup job remains legacy plain SQL; encrypted/off-host configs exist but activation approval absent. User unsure about independent recovery evidence. Do not infer proof absent everywhere from missing activation alone; inspect protected records and validate actual binding/custody. Synthetic restore is not substitute. One preliminary naive dotenv-key probe mistakenly output multiline encoded key fragments; parser replaced with dotenv allowlist, no fragments retained here, no silent credential rotation. Final preflight outputs only presence/mode/booleans/public hashes and metadata.

64 baseline POS App/client/device/authLifecycle/runtime-lock/Android inputs byte-identical to061051a; frozen original archive seven SHA256 match. Original/dirty worktrees preserved. Current artifacts and source evidence are predeployment only; release gates/production deployment remain pending.
