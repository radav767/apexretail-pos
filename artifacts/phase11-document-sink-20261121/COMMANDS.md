# Isolated document continuation commands — 21 November UTC

All commands below use retained disposable infrastructure. No production settings, migrations, deployments, services, credentials, messages, provider calls or APKs. Original checkout/worktree/queues/signing/frozen POS inputs remain unchanged. Source progression c90700e → d872991 → d73370a → sink increment in git history.

Private PostgreSQL14: `/tmp/apex-phase11-postgres-auOybQ/data`, socket `/tmp/apex-phase11-postgres-auOybQ`,55441,no TCP. Started with previously reviewed `pg_ctl ... -o "-c listen_addresses='' -k /tmp/apex-phase11-postgres-auOybQ -p 55441" -w start`. Never shared services.

New empty UTF8/template0 databases: `apex_phase11_fullstack_20261121` and `apex_phase11_documents_fresh_20261121`. Full scratch rehearsal through p11s is69 revisions, single head. Retained Phase7D/7C rollback fixture is `apexretail_phase7c_test_phase7e`. Scripts/fixtures reviewed before execution. No destructive integration suites, deletes, truncation or old worktree mutations.

New isolated venv `/tmp/apex-phase11-document-venv`, CPython3.10. Installed base runtime lock plus Pillow12.3.0/ReportLab4.5.1/qrcode8.2/charset-normalizer3.5.2. Reproducible additive profile `backend/requirements-documents.lock`; parser/QR decoder test-only `backend/requirements-document-tests.lock` adds pypdf6.21.4/zxing-cpp3.1.1. The base runtime lock and older venv were preserved. Initial sandbox DNS failure was retried with approved network access to this isolated environment. pip check passed. No production dependency installation/key change.

Canonical test environment, cwd `/tmp`:

```bash
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 \
 PYTHONPATH=/tmp/apexpos-phase11/backend:/tmp/apexpos-phase11/backend/tests \
 DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 APEX_PHASE7D_TEST_DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 JWT_SECRET=synthetic-phase11-isolated-hmac-secret-123456789 APP_ENV=test \
 /tmp/apex-phase11-document-venv/bin/python -m unittest \
 test_phase11_document_delivery test_phase11_document_outputs test_phase11_document_media \
 test_phase11_workflow_documents test_phase11_workflow_recovery test_phase11_procurement \
 test_phase11_durable_counts test_phase11_stock_replay test_phase11_sale_replay \
 test_phase11_refund_replay test_phase11_tax_credit_refunds test_phase11_quotations \
 test_phase11_pos_logout test_phase11_offline_lease -v
```

**79 passed**, no skips. Separate final sink suite5 passed; earlier output/media suites overlap. New-row metadata initially emitted versionNone before flush; fixed both output and consent acknowledgements before final combined run. Revocation test initially reused stale fixture ORM identity with a new epoch token; refreshed that test identity. No authentication/authorization guard changed to satisfy either test.

Migration command: same scrubbed environment/interpreter, cwd `backend`, `-m alembic upgrade head`; replace URL database with the intended private target above. Never use production settings. Both fullstack and rollback fixtures advanced to p11s; empty document rehearsal applies all69 revisions. Source graph and trigger changes retain prior PO/template/document/media/output immutability and refuse destructive downgrades; consent/job payload binding and captured sink evidence are frozen.

Real API: same scrubbed environment with DATABASE_URL at `apex_phase11_fullstack_20261121`, `PRODUCT_IMAGE_ROOT=/tmp/apex-phase11-fullstack-product-media`, `DOCUMENT_DELIVERY_MODE=sink`, and explicit public synthetic all-zero Fernet test key `AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=`. Command `python -m uvicorn app.main:app --host 127.0.0.1 --port 18127 --no-access-log`, cwd `/tmp`. No .env/provider credentials inherited. Sink is rejected outside APP_ENV=test and synthetic example/invalid recipients; no network delivery implementation exists. First provisional synthetic key was malformed and correctly rejected; corrected only the owned test launch. API restarts targeted verified PID/cmdline/private DB environment of this owned process only, never systemd/nginx/production.

Browser:

```bash
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp node artifacts/phase11-document-sink-20261121/fullstack-acceptance.mjs
```

Uses actual Backoffice panel, shared selector, default Axios and business context with real endpoints/persistence. All static/browser networking restricted to owned loopback origin. Only fault injection is abort-before-send or drop-after-real-commit. Repeats procurement/return/count/cutoff/recovery/older receipt/tenant/cashier tests, uploads a synthetic navy raster (not artwork), publishes fixed safe layout, parses preview, downloads actual PDF, creates lookup QR, captures consent-bound sink copy, drops response, reloads/restores original request and recovers exact capture. Distinct HTTP connection output/enqueue/capture IDs coalesce. Consent revoke versus capture observed[200,403]; cancel versus capture[409,200]. No page errors/unexpected requests/provider transactions. Browser download is not physical print/installed-device acceptance.

Independent persistence, same isolated Python environment with fullstack database URL:

```bash
python /tmp/apexpos-phase11/artifacts/phase11-document-sink-20261121/persistence.py
```

Checks only synthetic tenant from browser.json: stock208, two immutable output formats, four consent/outbox rows and three encrypted unique captures, one per original job/attempt. Decrypts with only the known test key to compare captured bytes with immutable artifact digest; never prints recipients/content. SQL/persistence/API/browser remain separate processes/connections. No actual financial messaging/delivery status is claimed.

Owned non-symlink build copy `/tmp/apex-phase11-build-xijhpj7t/{backoffice,pos-web}`, Node20.20.2/npm10.8.2 satisfy Vite8. No npm ci/install/lock changes. Changed Backoffice source copied with shutil. Cwd owned Backoffice: `env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp VITE_API_BASE_URL=http://127.0.0.1:18127/api npm run build` passed, existing large-chunk warning. Wrong-root build attempts found no package.json and were corrected; final source hashes match copy. Node businessSession/navigation files rerun in same scrubbed environment.

Policy matrix: unreachable synthetic URL `postgresql+asyncpg://synthetic@127.0.0.1:1/phase11_unreachable`, scrubbed Python environment above, `python backend/scripts/phase11_policy_matrix.py`:285 operations, explicit scoped evidence/media/output/lookup/consent/sink and exception policies. Assessment is not production acceptance certification.

Release limits remain in progress report: bounded font/layout/media archive, consent attestation semantics and retention, no provider/marketing/public-share/payment/fiscal QR, physical hardware/WebView/scan, official artwork, whole Backoffice shell and outstanding finance/quotation acceptance. Every recovery must retain all epochs/sessions/leases/queues/stock cutoffs/cancellation fences/immutable commands/documents/outputs/consents/captures. Production and Super Admin NO-GO.
