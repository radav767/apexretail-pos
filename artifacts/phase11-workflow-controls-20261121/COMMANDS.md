# Isolated workflow controls verification — 21 November 2026 UTC

Source branch `phase11/baseline-reconciliation`; backend foundation `a1687ba` follows operator-confirmed `387b50a`. No production migration, service, credentials, messages, provider actions or Android output. All databases below are disposable synthetic fixtures on the owned PostgreSQL14 Unix socket; TCP is disabled.

Exact backend command environment (never inherit production settings):

```bash
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 \
 PYTHONPATH=/tmp/apexpos-phase11/backend:/tmp/apexpos-phase11/backend/tests \
 DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 APEX_PHASE7D_TEST_DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 JWT_SECRET=synthetic-phase11-isolated-hmac-secret-123456789 APP_ENV=test \
 /tmp/apexpos-phase11-tests.qlfdlS/venv/bin/python -m unittest \
 test_phase11_workflow_recovery test_phase11_procurement test_phase11_durable_counts test_phase11_workflow_documents \
 test_phase11_stock_replay test_phase11_sale_replay test_phase11_refund_replay test_phase11_tax_credit_refunds \
 test_phase11_quotations test_phase7_final_actions -v
```

Working directory `/tmp`. `backend-regressions.log`: 71 passed, no skips. Subsequently added held-return inspection cutoff: same environment, `-m unittest test_phase11_durable_counts test_phase11_pos_logout test_phase11_offline_lease -v`: 19 passed, no skips (`cutoff-revocation.log`). Final strengthened expiry/revocation recovery suite: `-m unittest test_phase11_workflow_recovery -v`, result in `recovery-final.log`. Totals overlap; do not sum them. Fixture chain Phase7D→Phase7C rollback inspected; no destructive integration suites.

Same environment, argument `/tmp/phase11-workflow-concurrency.py`, script retained as `concurrency.py`: independent connection equal receipts/returns/counts, distinct final receipt and over-return budgets, conflicting approval UUIDs, count versus GRN/sale/refund/transfer, opposite transfers in different products, cancellation versus original/late packet. Every race has a 30-second bound and exact stock assertions. Final `concurrency.json` records observed order, not a required scheduler order. Synthetic cash bookkeeping only, no external payment calls. Newly registered tenants retained in private fixtures.

Migration: same scrubbed Python environment, cwd `backend`, `-m alembic upgrade head`, DATABASE_URL and test URL both replaced with `apex_phase11_workflows_final_20261121`. Prior retained empty-template0 rehearsal applied revisions 1–66; `private-empty-migration67.log` applies p11q to that empty-schema rehearsal. Populated rollback fixture independently upgraded, `private-populated-migration67.log`. Initially p11q's provisional revision identifier exceeded Alembic's 32-character column and rolled back; final revision `p11q_workflow_cancel_fences` fits without changing that column/constraint. All new migrations refuse destructive downgrade.

Owned build copies `/tmp/apex-phase11-build-xijhpj7t/{backoffice,pos-web}` have actual non-symlink `node_modules`; tracked changed/new Backoffice source copied with Python shutil. No dependency install or npm ci. Node v20.20.2, npm10.8.2 meet Vite8 ^20.19 || >=22.12; unchanged dependency locks.

```bash
# cwd /tmp/apex-phase11-build-xijhpj7t/backoffice
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp VITE_API_BASE_URL=http://127.0.0.1:18117/api npm run build
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp node --test tests/businessSession.test.mjs tests/navigation.test.mjs
# cwd /tmp
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp node /tmp/phase11-workflow-browser.mjs
```

Build passed; existing >500kB chunk warning retained. Final two Node test files passed. Initial navigation file failed because its older assertion expected reusable localStorage bearer credentials; updated to existing sessionStorage/shared revocation behavior. Behavioral business-context test still verifies stale/cross-account context rejection and POS queue preservation. No application authentication guard changed for this test repair.

`browser.mjs` builds actual panel/shared selector in an isolated Vite fixture, uses actual business-context replacement and a renderer-generated synthetic preview. Chromium153 headless; all requests intercepted to owned loopback fixture, synthetic client sinks, no API server or provider. Passed StrictMode, same-UUID lost-response retry, separate PO draft/approval, unknown-versus-zero count input, save/submit/approve separation, malformed ack retention, exact committed review, immutable template/document controls, sandboxed escaped renderer preview and late account reply isolation. `browser.json` has no unexpected requests/page errors. This does not certify live API integration, installed WebView, physical printer or provider acceptance.

Policy matrix generated with env -i, same Python/PYTHONPATH, APP_ENV=test, synthetic JWT and unreachable DATABASE_URL `postgresql+asyncpg://synthetic@127.0.0.1:1/phase11_unreachable`, command `python backend/scripts/phase11_policy_matrix.py`. 276 operations; matrix remains assessment with explicit acceptance limits, not certification.

`frozen-pos-check.json`: all seven original frozen POS release-source inputs still match retained manifest SHA256. No POS/Android files changed in this increment. `source-hashes.json` records final changed/new application/test/script source used for verification; local build output is non-deployable.

Limits: first Backoffice controls are owner-account focused, online only; workflow lists show latest100, selected command history defaults100 (API history supports limit<=200/offset). Older receipt lookup/full-scale UX remains pending; evidence is retained. Counts bound scope/dimensions at5000 and fail explicitly above the bound. Held/unassigned discrepancies require original inspection/assignment and explicit recount. Purchasing receivers need existing cost visibility; blind receiving pending. Supplier return is stock evidence, not AP/vendor credit/payment reconciliation. Text templates/snapshots only: media/logo/designer/server PDF/QR/delivery, installed devices and hardware remain uncommissioned. Existing split-tender, paid-credit payout, broader tax/report and quotation revision/discount/unit/currency limits persist. Super Admin and production NO-GO. Forward recovery must retain all identity/session revocation, leases, transaction proofs, cutoffs, cancellation fences, documents and original offline queues.
