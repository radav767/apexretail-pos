# Finite release P0 work — 27–28 November 2026 UTC

Operator-pushed base85c9ba124f8e02be8bf5033df5cfc445b2cbc572. No optional features/Super Admin commissioning. Current decisions and finite next work: docs/PHASE11-RELEASE-P0-STATUS-2026-11-28.md and docs/PHASE11-LIMITED-RELEASE.md. This is preparation evidence, not a deployed/final frozen candidate or all-P0 completion.

## Genuine recovery/configuration review

`env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp python3 artifacts/phase11-release-gates-20261127/recovery_evidence.py` and `verify_recovery_config.py`: read protected JSON/public pin records, allowlisted booleans/status/hash summaries; no provider contact/decrypt/upload/restore/backup activation. Config parser validates public-recipient fingerprint and protected Drive credential syntax without exposing values. Only public keybox bytes copied to a disposable /tmp GnuPG home; gpg metadata verifies configured primary/current encryption eligibility. No source GnuPG invocation or trust-store modification. Historical source encrypted dump/baseline SHA256 actually checked; source manifest restore_verified=false. Protected search/diagnostic/confirmation hashes match. No raw credentials/private keys, production rows or private-key fragments retained.

Current3AFF…2793 recipient and earlier synthetic owner-key recovery are distinct from historical missing4447…F95F. Full current off-host restore/config/media proof remains absent from inspected records. Source scheduled directory empty/activation absent; installed job still legacy plain SQL. Search scope bounded, not proof no receipt exists elsewhere. Operator acknowledgements do not provide custody/access/device/queue clearance. Exact required current-key custodian/recovery-host and newer genuine evidence paths are in the P0 status doc. Do not repeat synthetic recovery or generate keys/owner declarations speculatively.

Updated production_preflight.py **never uses inline signing keys**: excludes them from candidate Settings and requires effective file/credential source. In-memory key/public-ring pair+deadline check, no key output. Exclusive public-ring export was approved to /tmp/apex-phase11-independent-release-5lrb0b7l/effective-production-public-keyring.json; exact hash in manifests. Final command:

```
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp /tmp/apex-phase11-release-qualified-311/bin/python artifacts/phase11-limited-release-20261127/production_preflight.py
```

Production DB queries only metadata in asserted REPEATABLE READ READ ONLY before queries. Source194 files/lock unchanged; p10a,79tables/24triggers, PostgreSQL14.24. App role no superuser/create-role/create-database, but schema CREATE true and29 tables app-owned/50postgres-owned; API UID0. These remain real compatibility/security gates. No owners/grants/services/credentials modified. Public config/unit/dotenv hashes are consistency evidence, not private values or recovery custody.

## Rich corpus and sealed migration workflow

Only retained private PostgreSQL /tmp/apex-phase11-release-pg-ysjagwtm/data/socket55443 restarted, listen_addresses empty/no TCP. Created new databases apex_phase11_release_rich_upgrade and apex_phase11_release_rich_qualification; no old DB overwritten. `rich_fixture.py seed` refuses other DB names/p10a mismatch/nonempty companies. Generic helper fixture uses synthetic context/data only.30 rows/78 original tables cover2tenants, identities/POS revocation, open shift, cash/credit/refund/collection/debt, stock/balance, pending original print and quarantined queue. Seed is preservation corpus, not service posting acceptance.

Final supported-runtime run:

```
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp /tmp/apex-phase11-release-qualified-311/bin/python artifacts/phase11-release-gates-20261127/qualify_guard.py
```

Driver uses env-i APP_ENV=test/synthetic JWT and exact private URL `postgresql+asyncpg://postgres@/apex_phase11_release_rich_qualification?host=/tmp/apex-phase11-release-pg-ysjagwtm&port=55443`: alembic upgrade p10a; new rich seed; seal current source/runtime; exercise guard; controls. All steps pass. Separate synthetic-only app role NOLOGIN/CONNECT+CREATE fence; postgres-owned tables. **Does not mirror real production's29app-owned tables/CREATE privilege.**

prepare_guard_rehearsal.py builds a new owned /tmp/apex-phase11-guard-payload-* with tracked backend/migrations/locks, copied vendor-checksummed CPython3.11.18/base stdlib and qualified dependencies. Symlinks dereferenced, optional venv lib64 alias removed, bytecode writes disabled, all files manifest-pinned. Root/private plan and synthetic-only bounded clearance bind base development commit+explicit working payload, original queue hash/open-shift1. They are not final clean-source provenance or genuine production clearance. Production plan packaging/review remains mandatory.

New ops/phase11/release_guard.py validates pinned paths/payload/runner/snapshot/interpreter, no extra/nested-manifest/symlink files, private evidence, real DB owner/connection/DDL fence, locks, current queue/open-shift/source clearance. Production branch additionally requires protected matching custody/offhost/restore/config-media review receipts and inactive API/watchdog. No service, permission, credential, provider, release-switch or restore action exists in the runner. Never invoke old Phase10 pinned runner.

Qualified guard intentionally stops75 after5 ordered revisions, resumes24 to p11ac. Every original-column hash/numeric control/owner/ACL/current role/open shift/enforcement/trigger/function check passes;51 original function hashes preserved. Invalid indexes/unvalidated constraints rejected. Final stricter seal/head check and postgres worker read/import check pass separately (`final_guard_seal.py`; `check_worker_access.py`).5 fail-closed unit tests:

```
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 /tmp/apex-phase11-release-qualified-311/bin/python ops/phase11/test_release_guard.py -v
```

Snapshots/results remain private in the recorded /tmp guard directories; only synthetic summaries retained here. Current clearance rechecked per next migration and child timeout bounded by remaining window. Data drift/refused payload never triggers downgrade/old restore.

Earlier run_rehearsal uses the old small corpus; not counted again. Initial rich helper had a table/name collision (transaction never started); corrected. First3.10 payload generated unlisted pycache, so resume failed closed; fresh sealed payload corrected without changing DB guards. Final complete run uses current function-hash/index checks and supported3.11 runtime. Later stricter symlink/nested-manifest rejection has unit/head/worker checks, not a second claim of29 distinct migrations.

## Newer sales/revocation/output and interruption

`rich_forward.py before/after` was inspected and run with env-i PYTHONPATH=/tmp/apexpos-phase11/backend, APP_ENV=test, JWT_SECRET=synthetic-independent-release-secret-not-production-20261127 and DATABASE_URL `postgresql+asyncpg://postgres@/apex_phase11_release_rich_upgrade?host=/tmp/apex-phase11-release-pg-ysjagwtm&port=55443`, interpreter original private3.10 venv. Optional four modes unset/default-disabled. Actual ASGI endpoints create template/document/PDF, newer ordinary cash sale and logout-all; new process reads unchanged receipt/PDF, old token401/current fresh read200 and exact same-owner request200/original ID. No logging tokens. Existing original sale/stock/queue proofs never rebound.

Forward_guard.py deliberately tampers only the disposable source payload: rejected before DB, repaired forward with current snapshot. A separate owner process exits74 with uncommitted DDL/row; neither survives. Newer4sales/net35/user epoch1/original revoked POS session/original browser-queue hash remain. This is synthetic payload/transaction interruption, not a real systemd cutover/in-flight production migration kill or production recovery proof. Original retained snapshots/dump/queues untouched.

Fixture corrections: generic preupgrade active=false actors401; explicitly initialized active synthetic actors and ordinary SubscriptionService trial after upgrade before API acceptance. Correct402 unconfigured gate preserved. No fake provider renewal or test posting. Initial expectation that fresh same-owner exact replay403 was incorrect; existing policy allows original-ID recovery after current authentication. Final assertions check original credential401 and no duplicate side effect, no guard modified. Newer sale came through real API, not SQL insertion.

## Dependency security and supported runtime

Public registry/OSV calls initially hit sandbox DNS, then approved network retries; sent only public names/versions/lock data. No business providers. Raw pre-fix64 OSV records are summarized as public IDs/aliases/ranges (not64 distinct bugs). Python closure41 pins includes runtime+document profile; no test-tool/OS coverage claimed. Patched query returns0 records. npm production/all scopes as recorded return0 known findings after updates. Point-in-time advisory coverage is not proof of no vulnerabilities.

Public Python asset lookup initially per-file .sha256404. Actual publisher API digest used for exact release20261124 cpython-3.11.18 x86_64 GNU archive; SHA256 verified before bounded safe extraction under second exclusive /tmp attempt. No host/runtime install. Source copied public vendor metadata/provenance only. Host3.11.0rc1 deliberately rejected. CPython3.11.18 new /tmp venv installs candidate dnspython2.9.2/Pillow13 profile; existing runtime requirements otherwise unchanged. Backports-asyncio-runner requires<3.11; added explicit test-lock marker after install correctly refused it. Canonical candidate locks updated only after the new profile passed tests. Production3.10 environment/lock not changed.

From repo/backend, env-i PATH/HOME, PYTHONDONTWRITEBYTECODE=1, APP_ENV=test/synthetic JWT above, DATABASE_URL and APEX_PHASE7D_TEST_DATABASE_URL both `postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-release-pg-ysjagwtm&port=55443`:

```
/tmp/apex-phase11-release-qualified-311/bin/python -m pytest -q tests/test_phase11_user_sessions.py tests/test_phase11_remembered_sessions.py tests/test_phase11_identity_boundaries.py tests/test_phase11_sale_replay.py tests/test_phase11_stock_replay.py tests/test_phase11_financial_replay.py tests/test_phase11_procurement.py tests/test_phase11_durable_counts.py tests/test_phase11_reconciliation_exports.py tests/test_phase11_document_media.py tests/test_phase11_document_outputs.py tests/test_phase11_document_retention.py tests/test_phase11_auth_capabilities.py tests/test_phase11_offline_lease.py tests/test_phase11_tax_credit_refunds.py
```

80pass/32subtests/no skips, existing Pydantic warnings; pip check pass. Inspected fixture chain is explicit disposable DB whitelist + outer rollback/savepoint, no production settings inherited. Media tests use synthetic bounded/invalid formats; no malicious-image proof of every CVE claimed. Immutable historical stored bytes are not rerendered by dependency installation.

Node20.20.2/npm10.8.2. Only owned nonsymlink isolated node_modules directories used for `npm ci --ignore-scripts --registry=https://registry.npmjs.org`; no shared/symlink module install, root package-manifest change or APK build. Targeted lock updates resolve follow-redirects1.16.3, POSzod4.6.7 and affected dev glob/minimatch/rimraf closure. Actual loopback synthetic redirect tests3pass each include cross-realm sensitiveHeaders; Node auth8/lease11/entitlement7 pass. New redirect regression copied to isolated source before testing.

## Production-origin prepared artifacts

In /tmp/apex-phase11-independent-release-5lrb0b7l/source/{pos-web,backoffice}:

```
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp VITE_API_BASE_URL=/api VITE_BACKOFFICE_URL=https://backoffice.apexpos.cloud ENTITLEMENT_PUBLIC_KEYRING_FILE=/tmp/apex-phase11-independent-release-5lrb0b7l/effective-production-public-keyring.json npm run build
```

Both pass with known chunk warning. Final builds/public-ring source/hashes recorded in prepared-artifacts.json; no synthetic origin/key ID/private PEM/APK in prepared outputs. Earlier intermediate synthetic-origin dependency builds were not release artifacts and are superseded by these production builds. This does not qualify final POS offline journeys against production key custody or native devices. Exact final clean-source/config freeze pending permission/runtime/acceptance gates; do not ship merely because build passes.

495 source/actual-migration/lock/guard files hashed. Corrects previous403 manifest command's nonexistent backend/alembic path: actual backend/migrations now included. Archive migrations had never been omitted.63 baseline POS App/client/device/authLifecycle/Android inputs unchanged vs85c9ba1; frozen original seven hashes match. Candidate runtime lock intentionally changed for security; installed lock remains historical34b040… unchanged. Old/dirty worktrees, current signer, all queues/leases/proofs/revocations/immutable evidence preserved.

Checkpoint: tested source commit a9ca53bee2d8a0f59576651d2d3001e308b2fbf7;495 manifest entries independently match committed bytes. prepared-artifacts.json binds that development source, not final release qualification. `git push origin phase11/baseline-reconciliation` failed128 unavailable GitHub HTTPS Username; local work retained, no credential changes. Only owned private55443 cluster stopped via approved `env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp /usr/sbin/runuser -u postgres -- /usr/lib/postgresql/14/bin/pg_ctl -D /tmp/apex-phase11-release-pg-ysjagwtm/data -m fast stop`; no production process signalled. All synthetic data/queues/runtimes/builds/keys/archives/evidence preserved. Finite remaining P0 ledger is current, deployment HOLD.
