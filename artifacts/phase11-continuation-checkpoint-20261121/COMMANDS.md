# Retention / quotation / accounting continuation — 21 November UTC

Branch phase11/baseline-reconciliation; operator acknowledged83bb6d3. Tested implementation commits b5d74da (retention/Unicode/a11y), b2e6026 (revision lineage/UI),0bb23aa (review arithmetic/current credit proof). Final checkpoint adds injected revision rollback evidence. No production actions.

Read audit/checkpoint/current progress/document/procurement/split contracts and repository instructions; no AGENTS.md. Accounting invariants recorded before behavior changes in docs/PHASE11-RETENTION-TRANSACTION-CONTINUATION.md. No skills/delegation/external provider used.

Canonical tests, cwd/tmp, no inherited environment or .env:

```bash
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 \
 PYTHONPATH=/tmp/apexpos-phase11/backend:/tmp/apexpos-phase11/backend/tests \
 DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 APEX_PHASE7D_TEST_DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 JWT_SECRET=synthetic-phase11-isolated-hmac-secret-123456789 APP_ENV=test \
 /tmp/apex-phase11-document-venv/bin/python -m unittest \
 test_phase11_accounting_plans test_phase11_pricing_review test_phase11_credit_proof \
 test_phase11_finance_reconciliation test_phase11_tax_credit_refunds \
 test_phase11_quotation_revisions test_phase11_quotations test_phase11_document_retention \
 test_phase11_document_delivery test_phase11_pos_logout test_phase11_offline_lease -v
```

Combined46 passed, no skips; focused resource/permission/accounting suite8 passed afterwards. Final quote/revision suite11 passed after adding pre-commit child/items/proof rollback injection. Retention/media/output/delivery suite15 passed. Totals overlap; retain actual logs rather than add totals. Phase7D→7C rollback fixture chain inspected before tests; no destructive suites.

Separate-connection quotation script: same environment/Python, argument artifacts/phase11-quotation-revisions-20261121/concurrency.py. Equal and distinct revision IDs, parent/child and revision/conversion races, original sale/stock contention and post-conversion child-send denial,30sec bounds. Retained JSON records observed scheduler order; no provider action. Stock/payment effects occur only in existing synthetic native sale paths, never the new accounting planners.

Private cluster: retained /tmp/apex-phase11-postgres-auOybQ/data, PostgreSQL14, Unix socket55441/no TCP. Started with explicit listen_addresses='' and private socket. Migration: same scrubbed environment/interpreter, cwd backend, `python -m alembic upgrade head`. Existing rollback/fullstack fixtures advanced to p11u. New UTF8/template0 apex_phase11_retention_quotes_fresh_20261121 rehearsed all71 revisions. One source head p11u_quotation_revision_chain. No production schema inspected/modified. New migrations refuse destructive downgrade; forward recovery must retain all previous and new evidence/authority guards.

Owned API: uvicorn app.main:app on127.0.0.1:18127 only, DATABASE_URL at apex_phase11_fullstack_20261121; explicit APP_ENV=test, synthetic JWT, PRODUCT_IMAGE_ROOT=/tmp/apex-phase11-fullstack-product-media, DOCUMENT_DELIVERY_MODE=sink, public synthetic key AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=. No production settings/provider credentials inherited. Browser command `env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp node artifacts/phase11-retention-20261121/browser.mjs`; real panel/default client/endpoints/persistence plus archive/reactivation, keyboard and semantic preview checks; stock208, no page errors/unexpected requests. Quote revision UI separately uses intercepted synthetic client fixture artifacts/phase11-quotation-revisions-20261121/browser.mjs: same-ID retry, parent/child ack, late identity discard/pending retention. That fixture is not whole-shell/device acceptance.

Builds: Node20.20.2/npm10.8.2 verified, Vite8 requirement met. Tracked changed source copied via shutil into /tmp/apex-phase11-build-xijhpj7t/{backoffice,pos-web}; both node_modules are real owned directories, no npm ci/dependency lock changes. `env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp VITE_API_BASE_URL=http://127.0.0.1:18127/api npm run build` in owned Backoffice; same in POS with ENTITLEMENT_PUBLIC_KEYRING_FILE=/tmp/apex-phase11-build-xijhpj7t/test-public-keyring.json. Both passed; known large-chunk warnings. Shared revision source hash matches copy. Base runtime lock unchanged; pip check passed in retained isolated document venv. DejaVuSans packaged with license and fixed SHA; no official art generated.

Matrix: `python backend/scripts/phase11_policy_matrix.py` under scrubbed environment with unreachable synthetic DATABASE_URL=postgresql+asyncpg://synthetic@127.0.0.1:1/phase11_unreachable:290 operations, explicit revision/retention/proposal/current-ledger-read policies. Matrix is not acceptance certification.

Push: `env GIT_TERMINAL_PROMPT=0 git push origin phase11/baseline-reconciliation` failed128, HTTPS Username unavailable. Continued independent local rollback-test/evidence work. No credentials changed. Final source hash/frozen seven original POS checks retained. git diff against83bb6d3 is empty for frozen login/auth/client/device inputs, Android and base runtime lock. No original queue/data/source checkout overwritten.

Cleanup stopped verified owned loopback API PID1370096 after checking cmdline and private DB environment, then only owned private PostgreSQL with pg_ctl fast shutdown. Data/venv/build fixtures retained; no systemd/nginx/production process changes. Production/Super Admin remain NO-GO.

Posting limits: split tender calculations are not a posted sale/refund or acceptance. Discount/custom-unit/non-two-decimal quote review is a proposal with posting/conversion disabled; saved/accepted checkout parity remains gated. Current receivable proof does not repair legacy evidence or claim historical as-of balances. Font/shaping/tagged PDF/media retention/full-shell/device/hardware/provider/official branding and finance/quotation release limits remain in progress report. Every forward recovery must retain revocation, leases, original queues, stock cutoffs, cancellation/command/document/consent/capture and lineage proofs.
