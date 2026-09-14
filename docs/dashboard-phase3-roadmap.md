# Dashboard Phase 3 roadmap

Status: approved for local implementation on `phase3/dashboard-analytics`.
Production release remains separately gated.

## Objective

Turn the Phase 2 financial summary into consistent, explainable analytics. Every
card, comparison, trend, breakdown, drill-down, and CSV export must use one
accounting population and the same company, shop, and Africa/Harare date bounds.

## User-facing scope

- Sales and gross-profit trends grouped by day, ISO week, or calendar month.
- Current-period comparison with the immediately preceding period of equal
  inclusive length, including amount and percentage changes.
- Ranked product and category results by revenue, quantity, and gross profit.
- Payment-method, shop, cashier, discount, and refund breakdowns.
- Paginated contributing-sale drill-downs from dashboard analytics.
- CSV exports whose filters and accounting results match the screen.
- Explicit `Unavailable` discount analytics when any contributing original sale
  lacks a persisted `sales.discount_amount` snapshot.

## Accounting contract

- An original transaction is a sale with no `original_sale_id` and status
  `completed`, `partially_refunded`, or `refunded`.
- A refund transaction has an `original_sale_id`, status `refunded`, and is
  recognized on its own transaction timestamp.
- Gross sales are original transaction totals. Refunds are the absolute value of
  refund transaction totals. Net sales are gross sales less refunds.
- Cost of sales is the signed sum of contributing `sale_items.line_cost`. Gross
  profit is net sales less signed cost of sales.
- Product/category revenue is signed `sale_items.line_total`; quantity and cost
  use signed item snapshots, so refunds reduce the original dimensions.
- Discounts sum original-sale snapshots only. A discount aggregate is available
  only if every contributing original sale has an explicit snapshot.
- Empty populations report known zero values, including a known-zero discount.
- All date boundaries are inclusive reporting dates in `Africa/Harare` and are
  converted to a half-open UTC timestamp interval for storage queries.

## Security and compatibility

- Owner users and owner/administrator employees may report; other employees need
  the `reports` permission.
- Every requested company, shop, sale, product, category, or employee dimension
  is scoped to the authenticated actor's company.
- The legacy summary route receives the same authentication and reports
  authorization as Phase 2. Its response shape is retained for known clients.
- Phase 2 `summary-v2` remains backward compatible.
- No POS checkout or Android persistence contract changes are planned.

## Acceptance criteria

1. Cards and Phase 3 analytics reconcile for the same filter and fixture.
2. Day/week/month buckets use Africa/Harare boundaries and deterministic labels.
3. The comparison range is the immediately preceding equal-length period;
   percentage change is unavailable when the previous value is zero.
4. Product, category, payment, shop, cashier, discount, and refund breakdowns
   reconcile to the centralized accounting population without sale/item fan-out.
5. Drill-down rows are stable, paginated, ordered newest first, and tenant-safe.
6. CSV content uses the exact same repository result as the corresponding JSON
   screen request, with spreadsheet-safe cells and stable headers.
7. Historical unknown discounts remain unavailable in cards and breakdowns.
8. Legacy, Phase 2, Phase 3, drill-down, and export routes reject unauthenticated,
   cross-company, and insufficient-permission requests.
9. Backoffice analytics are keyboard-operable, labelled, responsive at 320px and
   390px, and express loading, empty, unavailable, and error states in text.
10. Query plans and timings are recorded on an isolated representative fixture
    before any index or reporting structure is proposed.
11. Backend, migration-cycle, Backoffice, POS compatibility, browser, and mobile
    validation pass without accessing production or rebuilding an APK.

## Release gates

- Local completion does not authorize a push, migration, asset publication,
  service restart, APK build, or production access.
- Any database index must be supported by before/after isolated `EXPLAIN ANALYZE`
  evidence and introduced through an additive migration.
- Release requires exact-commit approval, verified backups, staged migration and
  health checks, semantic fixture checks, and separately approved rollback steps.
