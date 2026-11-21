# Synthetic atomic split checkout — 21 November UTC

Continues455e529 after operator push acknowledgement83bb6d3. No production or provider actions. Original accounting/refund/rounding contracts predate posting changes; default-disabled test-only API is not release acceptance.

Fixtures inspected: test_phase11_split_checkout→test_phase11_procurement→Phase7D→Phase7C isolated rollback fixtures. Canonical command, cwd/tmp:

```bash
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 \
 PYTHONPATH=/tmp/apexpos-phase11/backend:/tmp/apexpos-phase11/backend/tests \
 JWT_SECRET=synthetic-phase11-isolated-hmac-secret-123456789 APP_ENV=test \
 DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 APEX_PHASE7D_TEST_DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 /tmp/apex-phase11-document-venv/bin/python -m unittest \
 test_phase11_split_checkout test_phase11_sale_replay test_phase11_refund_replay \
 test_phase11_tax_credit_refunds test_phase11_finance_reconciliation \
 test_phase11_financial_replay test_phase11_quotations test_phase11_quotation_revisions \
 test_phase11_pos_logout test_phase11_offline_lease -v
```

Combined54 passed, no skips. Final focused7 passed after bounding new DTO positions; overlapping counts. ASGI calls real application routes/persistence, explicit synthetic settings patch only enables test-mode posting. Existing generic shape/fingerprints remain unchanged. Mixed cash/credit one-sale/stock/debt, tax penny residual and positive collection reconciliation, exact replay after expiry/disabled mode, changed input/config/total/tenant/credit authority denial, FX original cash change, atomic injected leg failure, immutable tender/sale/item snapshots and legacy split-refund denial covered. Default/production mode and card/offline reject. Does not certify UI/provider/report/receipt parity.

Separate connections: same scrubbed environment with SPLIT_CHECKOUT_MODE=test, same Python, script `/tmp/apexpos-phase11/artifacts/phase11-split-checkout-20261121/concurrency.py`. Bounded30-second gathers, isolated newly registered synthetic tenant. Three equal requests→one sale; distinct sales sharing leg IDs→[200,409]; shared customer credit-limit race→[409,200]. Three sales/six legs/three movements, stock97, original credit11. No providers. JSON/logs retained; scheduler order is observed, not assumed.

Private PostgreSQL14 no TCP, socket/tmp/apex-phase11-postgres-auOybQ:55441. Restarted only retained owned cluster. Applied p11v/p11w only to rollback DB. New `apex_phase11_split_fresh_20261121`, template0/UTF8, created with `sudo -u postgres psql -h /tmp/apex-phase11-postgres-auOybQ -p 55441 -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE apex_phase11_split_fresh_20261121 TEMPLATE template0 ENCODING 'UTF8'"`. Same scrubbed environment with DATABASE_URL changed to new DB, cwdbackend, `python -m alembic upgrade head` applies all73 revisions, head p11w_split_snapshot_guards. Deferred totals/ownership/credit and immutable sale/item/leg guards are additive; destructive downgrade refused. No production schema inspected or changed.

Matrix regenerated with unreachable synthetic DATABASE_URL=postgresql+asyncpg://synthetic@127.0.0.1:1/phase11_unreachable using `python backend/scripts/phase11_policy_matrix.py`:291 operations. Explicit synthetic split policy, gaps retained. No frontend build needed: no frontend/package changes. All venv/base locks/Android/auth helpers/original queues untouched.

Limits: test-only online cash/credit (including configured cash FX), two-decimal base; no split refunds or collection-backed paid-credit payouts, provider intents, cards/mobile/offline authority, whole UI, receipt/report/shift parity or production enablement. Production/Super Admin NO-GO. Forward recovery preserves every existing revocation/lease/queue/cutoff/cancellation/command/document/consent/lineage safeguard plus original tender/sale/item evidence.
