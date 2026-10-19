# Phase 7D — Multi-business and restaurant operations

Status: development review candidate. NOT deployed; no production migration or APK build performed. Operational limits below must be accepted or completed before rollout.

Base: Phase 7C `f880817b3af8eeeff890a54c27c66d1affc55552`.
Branch: `phase7d/multi-business-restaurant`. Exact candidate commit and checksums are recorded in packaged `release.json` and `SHA256SUMS`.

## 1. Existing implementation audit

| Existing area | Finding | Phase 7D approach |
|---|---|---|
| Business types | Registration and Settings already stored a free-text company business type | Recognize seven profiles without backfilling or rewriting existing companies; preserve legacy/custom labels until an authorized settings change |
| Products / Phase 7A | Standard/non-stock/service/composite/variant products, customer price levels, bulk thresholds, units and case breaking already exist | Reuse product identity, configured pricing and checkout; no replacement product/inventory engine |
| Employees / Phase 7B | Canonical backend permissions, custom roles, scoped POS sessions and action-specific manager approval exist | Add operational permissions/presets; preserve authentication and explicit existing restrictions |
| Printing / Phase 7C | Durable station-bound print jobs, immutable snapshots, product/category routing and delivery review exist | Feed pre-payment order tickets into the same queue; prevent settlement from issuing duplicate preparation tickets |
| Restaurant | No authoritative unpaid order/table/KDS lifecycle existed | Add explicit operational records separate from completed sales |
| Hotel | No room/guest folio model existed | Add optional rooms and customer-linked guest accounts, not bookings/reservations |
| Pharmacy | No lot/expiry provenance existed | Add opt-in batch assignment and allocation against existing stock movements; never fabricate historical batches |

## 2. Implemented features

### Business profiles

- Retail / Supermarket; Restaurant / Café; Bar / Nightclub; Hotel / Hospitality; Pharmacy; Hardware / Wholesale; General Business.
- Registration options and existing Backoffice Settings selection support these labels. Dedicated Business Profile controls configure operational features and optional tip/service products.
- Existing company labels and configuration are unchanged by migration. Unknown/custom labels retain general functionality. Choosing a profile does not remove existing POS/Backoffice modules.
- New feature grids show relevant operational pages and permissions, using the approved dark-green design.

### Restaurant

- Tables, named floors, seating and responsive coordinate layouts; add/edit/deactivate with branch isolation and protection against disabling tables with open bills.
- Authenticated waiter assignment, table transfers, open orders, versioned item additions/removals and preparation notes. Variants retain their identity.
- Requests have stable identities; stale concurrent edits return a conflict rather than overwrite another employee's work.
- Kitchen/bar dispatch before payment. Product/category station routing, delta quantities, negative cancellation tickets and immutable ticket snapshots reuse Phase 7C delivery jobs.
- Repeating Send with no changes produces no additional tickets. Sending an unpaid order does not create a sale, payment or inventory movement.
- KDS/bar pages, ten-second refresh, branch/role filtering and permitted status transitions. Cancellation amendments put obsolete preparation tickets into `needs_review`, blocking preparation from old quantities. Informational/cancellation updates are acknowledged rather than marked as newly cooked food.
- Prepared table/waiter transfers queue zero-quantity informational updates; KDS uses the current table/waiter while preserving the original ticket snapshot.
- Whole-line split bills, compatible bill merges and table transfers, with row locks, version checks and protected audit events. Sent quantities move with lines; splitting/merging does not prepare or deduct stock again.
- Final payment invokes the existing sales service in the same transaction as order closure. Sale identity is bound to the server order ID; concurrent/retried settlement returns the same sale. Stock is deducted by the existing sales engine exactly once.
- Configured customer price levels and quantity thresholds are reused for estimates and revalidated at checkout. Duplicate product lines with different kitchen notes are grouped for the existing checkout contract.
- Existing discounts, currency validation, stock/composite/variant deductions, customer credit and manager discount approval remain authoritative. The existing subscription write gate is enforced on the new settlement route.
- Tips/service charges can be configured as authorized, active non-stock/service products. Their existing price and tax rules apply; they do not generate kitchen preparation tasks.
- Existing receipt reprinting and station auto-receipt dispatch are connected. Settlement cannot create another sale-based KOT for an order already sent before payment.
- Restaurant reporting reads persisted sales and linked refunds, keeps unlike currencies separate, and uses the company's reporting timezone. Existing financial reports remain unchanged.

### Optional hotel / hospitality

- Rooms can be created, edited and suspended without deleting history.
- Guest accounts link a room to an existing tenant customer. One active guest account per room; authorized close is blocked while open orders or customer credit remain outstanding.
- Room-service orders use the restaurant lifecycle and kitchen/bar queue.
- Charges to rooms use the existing customer-credit sale and receivable model; they do not invent a new payment method or independent debt ledger. Existing customer credit limits/permissions apply.
- Guest billing shows posted charge/refund records and existing outstanding balances, with settlement through the existing Credit Settlement module.
- No bookings, reservations, nightly rates, room inventory calendar or prescription/regulatory workflow was invented.

### Pharmacy / batch tracking

- Batch code, explicit expiry date, branch/product assignment, available quantity, thirty-day expiry indicators and CSV stock reports.
- Batch assignments allocate already received physical stock; they cannot increase aggregate stock or exceed its unallocated quantity. The assignment is audited, not backfilled into historical receipts.
- For products with assigned batches, FEFO allocation links negative existing inventory movements to unexpired lots. It supports ordinary sales and standard composite components without introducing a second stock deduction mechanism.
- Sales with insufficient unexpired assigned lots fail atomically. Refunds/receipts remain unallocated until inspected; unknown lot/expiry information is never guessed.
- Existing products without batch assignments retain their prior inventory behavior. The UI explicitly warns that unassigned stock is not expiry-verified.

### Wholesale

- Quotations: customer, variant/product lines, quantities, price estimates, browser printing/PDF saving and conversion through existing checkout.
- Phase 7A customer price levels, bulk minimum quantities, unit conversion and case-breaking remain in use; no duplicate pricing or inventory subsystem.
- Quotations are non-financial estimates. Final configured pricing and taxes are revalidated at conversion; no promise of locked contractual quotation pricing is made.

## 3. Permissions and safety

- New permissions: restaurant management; own open-order management; kitchen dispatch; bill settlement; kitchen/bar viewing and status updates; hospitality management; batch viewing/management; quotations.
- Waiter and kitchen presets extended; bartender, restaurant manager and hotel staff presets added. Custom roles retain explicit permissions, and unknown/inactive custom roles do not inherit the new kitchen powers.
- Employee reads/actions remain tenant/branch scoped. Waiters cannot edit another waiter's order without management permission; employee settlement and printer delivery are register-bound.
- Online PIN login accepts authorized operational staff without granting sales access. Non-sales staff are routed away from checkout, the Sales navigation entry is hidden, and sale submission remains permission-guarded. Existing offline PIN restrictions and signed offline authorization remain unchanged.
- Operational pages are online-only. Connectivity loss disables writes; reconnection reloads authorization/profile state. New order recovery markers are separate, cashier/device-bound local metadata—not offline financial transactions.
- Existing offline queues, original timestamps, shift binding and quarantine rules are preserved. Batch-related synchronization rejection must retain the original queued transaction for review, never delete/reassign it.
- Costs, PINs, device activation secrets and financial account balances are not exposed through operational picker endpoints. Documents escape HTML/CSV input.
- Operational audits use the existing append-only audit system. No historical sale/financial association is fabricated.

## 4. Backend/API and database changes

Additive authenticated endpoints under `/api/operations` cover profiles, safe pickers, tables, orders/items, dispatch, transfers, splits, merges, cancellation, settlement, kitchen status, rooms, guest accounts/folios, batch assignment/reports and restaurant reports.

Existing API routes and request contracts remain available. The sales repository gains an optional non-committing mode for atomic order settlement. Sales/inventory repositories also gain a batch-allocation hook; original callers keep their commit behavior.

New migration: **`p7e_business_orders_batches`**, parent **`p7d_printers_kitchen_jobs`**.

```
p5h_runtime_write_permissions
  -> p7a_product_composites
  -> p7b_variant_pricing_tax
  -> p7c_employee_roles_permissions
  -> p7d_printers_kitchen_jobs
  -> p7e_business_orders_batches
```

Nine new tables: `business_profiles`, `dining_tables`, `hospitality_rooms`, `guest_accounts`, `commerce_orders`, `commerce_order_items`, `kitchen_tickets`, `product_batches`, `batch_allocations`.

One nullable `print_jobs.order_id` link. No data backfill, exchange-rate change, historical shift linkage, table-ownership change or schema CREATE grant. Runtime grants are limited to new objects; kitchen ticket identity and batch-allocation history cannot be updated/deleted by the runtime role.

Downgrade refuses populated Phase 7D operational/configuration tables. Reviewed forward recovery is required after operational use; do not drop populated data or restore an older database over newer transactions.

## 5. Verification

Final evidence is packaged with this report:

- Full backend: **320 passed, 122 subtests passed**, zero failed/skipped; six pre-existing deprecation warnings (Pydantic configuration, Starlette/httpx and Python string escapes).
- Phase 7D integration: **31 tests**, covering kitchen-before-payment, repeated dispatch, cancellations/review, KDS/bar isolation, stale edits, transfers, splitting/merging, settlement retries, real concurrent settlement, failure after sale flush, price levels, tips/service lines, guest credit/closure, FEFO, expired lots, composite allocation, subscription enforcement and restricted runtime privileges.
- POS and Backoffice: **23 regression/lint/build commands** pass, including existing printer JVM/source compatibility checks. Existing lint/build advisories remain; no new lint errors.
- Browser: **40 responsive checks** at 1440, 820, 390 and 320px; Back navigation, offline disabled controls and kitchen/non-sales access checks pass.
- **25 actual React screenshots** with synthetic preview data. Both apps use the same operational components; the preview shell uses synthetic shop/staff information and is not a deployed application. No production API calls were permitted during capture.
- Migration rehearsal on a separate synthetic clone: upgrade, empty-schema downgrade and forward recovery preserve hashes/counts of all **46 pre-existing tables**. Existing `print_jobs` fields are compared excluding only the new nullable column. Baseline totals: sales **1105.00**, stock **113.000**, historical shift links **0**, enforcement-enabled companies **0**.
- Populated-clone downgrade guard: downgrade refused; all **56 tables** and three committed synthetic orders remained unchanged.
- All databases used have explicit disposable names and were cloned from prior synthetic fixtures—not production. This does not substitute for a fresh protected production-clone rehearsal.

## 6. Remaining limitations / manual acceptance gates

1. New open orders, kitchen/KDS operations and restaurant settlement are online-only. Existing retail offline checkout/synchronization is preserved, not replaced with offline table-order synchronization.
2. Splits move whole lines, not fractions of a line or arbitrary tender amounts. No stock reservations, recipe wastage or automatic ingredient write-off is invented for unpaid/cancelled kitchen work. Existing authorized stock adjustments remain the accounting path; restaurant operations must define reservation/waste policies before broad use.
3. Tips and service charges use explicitly configured service products, not automatic percentage/compounding rules or a separate gratuity-liability ledger. Owner/accounting review of those products, pricing and taxes is required.
4. Quotations are estimates, not locked-price contracts; validity dates, approval negotiation and contractual price locking are not implemented.
5. Batch support is opt-in and currently restricted to standard/variable-weight stock products without variants; standard recipe components work through the same hook. Lot-specific receipt allocation, returning stock to an existing lot, disposal, batch transfers and lot stock-count reconciliation need further workflow work. Repeated receipts into an existing lot code are not supported by the assignment UI; do not invent replacement codes to bypass that limitation. Positive stock remains explicitly unallocated pending inspection. Pharmacy production readiness is **not claimed**.
6. Cancelling prepared items requires an explicit cancellation ticket and review of obsolete KDS tasks. Human verification is still required for food already prepared/served and for physical paper output. No full kitchen task-per-ingredient production system is claimed.
7. Rooms/guest credit are not a hotel booking engine. Guest closure conservatively checks all outstanding customer credit. Hotel-specific tax/rate/booking policies need a separate reviewed model.
8. Pickers are capped at 1,000 choices; order/KDS lists are bounded to recent 100 records. Larger installations need pagination/search extensions. Existing full sales/reporting modules remain available. Finish open operational work before changing the business profile; changing the selected type is not a data migration.
9. Bluetooth, USB, LAN, paper cutting, WebView behavior and real printers require physical acceptance. No APK was rebuilt/installed; LAN support still needs the separately authorized Phase 7C native APK update. A bridge/OS submission does not prove paper printed; uncertain jobs require authorized review.
10. Before deployment, review all pending Phase 7A–7D migrations on a protected current production clone, runtime grants, configuration/backups, role assignments, pricing/tax choices, online order policy and real cashier/printer workflows. Coordinate backend/frontend release only after separate approval. Mandatory shift enforcement must stay unchanged/off.

## 7. Delivery and production safety

See packaged gallery, source archive, exact changed-file list, test logs, migration evidence, builds and SHA-256 manifest. Production database, services, frontends, currency settings, signing configuration, installed APKs and existing queues were not modified. No production transactions were created. This report requests review, **not deployment authorization**.
