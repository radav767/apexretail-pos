# Split receipt disclosure and software output parity — 21 November UTC

Follows dated-flow/shift commit eee7c96. Push `env GIT_TERMINAL_PROMPT=0 git push origin phase11/baseline-reconciliation` failed128, HTTPS Username unavailable. Continued independent receipt implementation/tests afterwards; no credential changes. Synthetic development only; production and Super Admin NO-GO. Split posting remains default-disabled/test-only, no new checkout controls or provider/card/mobile/offline authority.

Original immutable tender/refund evidence now supplies split-receipt-v2 to native receipt reads and newly queued print jobs. Labels distinguish cash payment, original unpaid credit, cash refund and debt reduction; never substitute current debt/rates or a scalar paid total. Original currency/change/base amounts/rates/config remain frozen. New direct split receipt and cached print recovery additionally revalidate current actor/epoch/register context. Existing print jobs return original payload/hash before rendering; new source documents freeze ordered payment rows, avoiding JSON object key reordering. New split-only HTML renderer5/PDF layout3-split; older document/output lookup returns stored bytes without regeneration. Old non-split input/proof/queue formats unchanged.

Canonical backend environment and inspected rollback fixture chain are exactly those in ../phase11-tender-flows-20261121/COMMANDS.md: env-i, private apexretail_phase7c_test_phase7e socket55441, APP_ENV=test/synthetic JWT, isolated document venv, cwd/tmp. No inherited .env/provider settings. Commands:

```bash
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 \
 PYTHONPATH=/tmp/apexpos-phase11/backend:/tmp/apexpos-phase11/backend/tests \
 JWT_SECRET=synthetic-phase11-isolated-hmac-secret-123456789 APP_ENV=test \
 DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 APEX_PHASE7D_TEST_DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 /tmp/apex-phase11-document-venv/bin/python -m unittest \
 test_phase11_split_receipts test_phase11_document_outputs test_phase11_workflow_documents \
 test_phase11_document_retention test_phase11_split_checkout test_phase11_split_refunds \
 test_phase11_split_shifts test_phase11_tender_flows test_phase11_sale_replay \
 test_phase11_refund_replay test_phase11_pos_logout test_phase11_offline_lease -v
```

Combined57 passed, no skips. Final direct-identity/receipt/document focus3 passed after adding anonymous/stale-epoch denial. Prior document/retention/output focus11 passed. Counts overlap. Real API/persistence/print-queue source equality, credit collection and partial mixed refund, original disclosure unaffected by later debt/status, frozen job recovery without snapshot recomputation, wrong tenant, anonymous/stale direct calls,58/80/A4 parser text, mixed refund A4 debt/cash rows, and unchanged saved HTML/PDF after later collections/refunds verified. Initial SourceBlock fixture incorrectly supplied text and was correctly422; corrected input. Initial PDF dictionary totals reordered rows in JSONB; replaced new split disclosure with an ordered list. Narrow-paper assertion exposed the numbered prefix splitting a phrase; ordered dedicated rows remove that prefix. No weakening of document/font/resource guards.

Fixture JSON is actual synthetic persisted queue payload (no credentials/provider data), exported by final backend receipt test. Node/renderer tests use the same file. Node20.20.2/npm10.8.2 reconfirmed; owned /tmp/apex-phase11-build-xijhpj7t/pos-web/node_modules verified actual non-symlink directory. Copied only changed source/scripts/tests there; no npm ci/install or dependency lock changes. In owned POS copy:

```bash
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp \
 PHASE11_SPLIT_RECEIPT_FIXTURES=/tmp/phase11-split-receipt-fixtures.json PHASE11_SPLIT_HTML_DIR=/tmp \
 node scripts/run-split-receipt-tests.mjs
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp node scripts/run-receipt-discount-tests.mjs
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp node scripts/run-auth-lifecycle-tests.mjs
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp VITE_API_BASE_URL=http://127.0.0.1:18127/api \
 ENTITLEMENT_PUBLIC_KEYRING_FILE=/tmp/apex-phase11-build-xijhpj7t/test-public-keyring.json npm run build
```

Split TS/Node tests passed: actual API/queue disclosure equals58/80mm HTML/thermal values, exact integer minor units, missing/altered/unsafe fields fail closed without scalar Paid, large valid-boundary read-only rendering fixture retains full credit identification and amount on32 columns. Existing discount renderer checks passed;8 auth lifecycle tests passed. Full POS TypeScript/Vite build passed, known chunk warning. Initial Node attempt read an older temporary fixture before refreshed backend export; reran sequentially after backend completion. No application failure inferred from that fixture ordering mistake.

Browser: `env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp node artifacts/phase11-split-receipts-20261121/browser.mjs`, isolated Playwright/Chromium, all network requests aborted, finally closes browser. Four actual formatter preview fragments (original/refund58/80), ordered dl/dt/dd values equal persisted queue payload, no scalar Paid, no horizontal clipping, software A4 print PDFs. Zero page errors/unexpected requests. Backend separately creates/parses immutable58/80/A4 PDFs and checks retained bytes. These verify software output/fragments, not complete POS/Backoffice shell, installed WebView, printer, fiscal or provider acceptance. No printer invoked or APK published.

Candidate App.tsx has exactly two receipt-only additions: typed optional split metadata and conditional pass-through into receipt snapshot. No login/bootstrap/authorization/device/lease/offline queue code changed; original frozen release's seven hashes still match. Other frozen auth/device helpers, Android and runtime lock unchanged against7628252. Existing archived snapshots/queue keys retained; missing split evidence requires review. Saved documents/outputs/consent never rewritten. No schema/dependency change; prior76-revision rehearsal current. Matrix294 operations regenerated against unreachable synthetic DB with receipt evidence scope explicit. pip check/source whitespace pass; source/frozen hashes retained.

Remaining acceptance: full first-party shell/API receipt interactions, Backoffice entry points and independent print/output/UI identity-change concurrency before split UI consideration; hardware/provider commissioning separately unavailable. Continue saved quotation discount/configured-unit/currency accepted conversion afterward. All collection-backed payout/provider/card/mobile/offline and prior finance/document/device limits remain. Every forward recovery retains revocation, signed leases, original queues, command/lineage/cutoff/cancellation/tender/refund/immutable document and consent evidence.
