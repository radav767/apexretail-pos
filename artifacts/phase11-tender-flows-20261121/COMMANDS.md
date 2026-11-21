# Dated tender flows / split shift reconciliation — 21 November UTC

Continues operator-confirmed7628252 on phase11/baseline-reconciliation. Read audit/checkpoint/current progress and accounting/split/document contracts, no applicable repository AGENTS.md. Wrote docs/PHASE11-TENDER-FLOW-RECONCILIATION.md before behavior changes. No skills or delegation. Synthetic development only; no production deployment/migration/services/credentials/provider/message/APK actions.

Owned private PostgreSQL14 at /tmp/apex-phase11-postgres-auOybQ/data restarted only with listen_addresses='' and private socket55441. Retained rollback DB apexretail_phase7c_test_phase7e at p11z (76 revisions). No new migrations/dependencies. Reviewed test fixture chain TenderFlowTests/SplitShiftTests→SplitRefundTests→SplitCheckoutTests→Procurement→Phase7D→Phase7C; rollback-scoped synthetic fixtures, no generic inherited settings.

Canonical combined command, cwd/tmp:

```bash
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 \
 PYTHONPATH=/tmp/apexpos-phase11/backend:/tmp/apexpos-phase11/backend/tests \
 JWT_SECRET=synthetic-phase11-isolated-hmac-secret-123456789 APP_ENV=test \
 DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 APEX_PHASE7D_TEST_DATABASE_URL='postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7e?host=/tmp/apex-phase11-postgres-auOybQ&port=55441' \
 /tmp/apex-phase11-document-venv/bin/python -m unittest \
 test_phase11_tender_flows test_phase11_split_shifts test_phase11_shift_commands \
 test_shift_reports_api test_phase11_split_checkout test_phase11_split_refunds \
 test_phase11_split_history -v
```

Combined39 passed, no skips. Later focused dated-flow/shift/native-tax-credit13 passed, no skips. Final provenance/revocation/shift focus8 passed, no skips; counts overlap. First fixture assumed an unstated cost2 and submitted duplicate product lines (correctly400); corrected to explicit cost and two distinct products. Close replay initially compared equivalent .00/.0000 strings, corrected to monetary Decimal equality while preserving full metadata comparison. No application guard weakened.

Report GET /api/reports/tender-flows/{company}: timezone-aware half-open <=366day UTC bounds, original sale/refund.created_at versus collection.received_at. Current identity/revocation/revenue+collection permission and event-owned branch/shift scope. Single SQL snapshot, independent sale/item-cost, tender, refund and collection aggregates; paginated detail/full-window totals, stored base/currency grouping. Missing legacy originals/rates/costs flagged, unknown physical cash excluded from known totals. Original payment, credit origination, collection, paid refund, debt reduction distinguish revenue, payment and debt. Allocation FX residual versus separate tender/change conversion residual disclosed with explicit equation; no hidden fee/debt or current-rate reconstruction. Local accounting is never provider confirmation.

Shift original currency sums add split tender-minus-change and only paid refund allocations. Applied-base summary adds partial credit separately and excludes debt reductions from cash paid out. New split cash legs/refunds require target open-shift currency/cash/precision snapshot or409 before commit. Closed currency/count/summary data remain frozen; detailed recovery reads stored close summary. Existing revocation/register/lease/offline/proof behavior preserved. Base current summary is applied accounting; original units govern physical drawer counts.

Independent connections: same scrubbed environment/Python with SPLIT_CHECKOUT_MODE=test and `/tmp/apexpos-phase11/artifacts/phase11-tender-flows-20261121/concurrency.py`. URL explicitly asserts owned DB/socket/port. New synthetic registration/stock/debtor/opaque cashier per run. Close-winning sale/refund races [409,409,200]. Controlled posting-first and refund-first transactions hold shift while close waits; final expected physical balances28 and20, respectively. During staged uncommitted sale header/debt/proof and refund allocation transactions, another connection sees only complete previously committed report state. Three equal committed sale/refund recoveries after close return one original receipt. Bounds10/20/30sec; no provider/hardware action. JSON/log preserve observed scheduler outcomes.

Report tests: original/collection/refund on three distinct days, exact boundary exclusion and timezone offsets, two distinct items/two collections/two legs without multiplied billed/cost sums, exact sale/collection/refund replay, expiry/disabled reads, partial refund/debt separation, FX thirds producing both distinct one-cent residuals and final zero original cash units, missing legacy snapshots and revoked reader denial. Shift tests: opening20+cash8+collection1-paid refund3=26, debt reduction3 excluded; exact immutable close/replay; configured FX cash16 (tender20/change4), partial/final original-currency payouts4/12, inactive currency retained in snapshot, zero final physical variance; late currency or changed precision rejected with stock unchanged. Historical UI/printed/device receipt parity remains separate.

Matrix regenerated using same scrubbed interpreter and unreachable synthetic DATABASE_URL=postgresql+asyncpg://synthetic@127.0.0.1:1/phase11_unreachable, `python backend/scripts/phase11_policy_matrix.py`:294 operations. Source whitespace passes; hashes retained. No frontend changes/build for this increment. Split posting remains default-disabled/test-only. Production and Super Admin NO-GO. Receipt/printed/UI acceptance, saved quotation discount/configured-unit/currency accepted conversion, collected-credit payouts/providers/cards/mobile/offline and prior finance/document/device commissioning gates remain. Every forward recovery retains all revocation/queue/lease/transaction/tender/refund/immutable document safeguards.
