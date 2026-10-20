# Phase 7E integration review — 20 October 2026

Historical first-pass report at `ff05b36`. The continuation and current tip,
recovery and pharmacy-return findings are in `PHASE7E-TIPS-AND-RECOVERY.md`.

Status: PARTIAL / NO-GO for production. This is an isolated development candidate,
not completion of every Phase 7E objective. No deployment or APK build occurred.

## Baseline and safety

Branch: `phase7e/integration-functional-completion`, isolated worktree
`/tmp/apexpos-phase7e`, based on clean Phase 7D commit
`4f2109dffff642422e046dde9147f7d0c89d759d`. Earlier Phase 7A–7D work is inherited,
not recreated. The main worktree and its untracked files were preserved.

No live production database connection, schema change, business-data write,
service restart, asset publication, signing operation or APK packaging was used.
Existing financial/offline queues and printing paths are not cleared or replaced.
No currency or mandatory-shift-enforcement setting is changed.

## Implemented and verified

- Checkout pricing now reselects configured quantity tiers when adding/changing
  standard, weighted or variant quantities. A variant retains its original base
  price separately, so removing customer pricing restores retail rather than a
  stale discounted price. Existing monetary arithmetic and server pricing remain
  authoritative. Pricing tiers remain product-level, not a new per-variant tariff.
- The server rejects a missing variant when active variants exist, rather than
  allowing an older client to deduct parent stock instead. Existing completed
  retries are resolved before this new-sale check. Old queued non-variant sales
  affected by later catalog changes need authorized review, never silent
  reassignment; businesses with no configured variants retain their old behavior.
- Repeated weighted-product additions now merge into one cart line using the
  existing fixed-point quantity helpers, check combined available stock and
  reselect the applicable price tier. Boundary/overflow tests cover the helper;
  physical weighing/scanner checkout still needs manual acceptance.
- Bill splits accept explicit positive quantities, while keeping the old
  `item_ids` request contract. Validation prevents unknown/duplicate/excess/all-item
  splits. Quantity and already-dispatched preparation quantities are conserved.
  Pending kitchen amendments must be dispatched before splitting a prepared bill.
  Both resulting bills settle through the existing sales engine; retries do not
  create extra sales or deduct stock twice. Draft prices are estimates and each
  bill's customer pricing is revalidated at settlement, as before.
- Offline **unpaid restaurant drafts** have a separate persistent cashier/company/
  register-bound outbox. Original payloads/timestamps survive retries and restart
  storage tests. Per-command keys avoid a shared-array append overwrite. No
  financial sales queue is touched. Conflicts/authentication rejection retain the
  original command for review. A synchronization timeout retries the same ID.
- New authenticated, entitlement-gated `/api/operations/offline/drafts` and
  `/api/operations/offline/edits` endpoints revalidate current permissions and the
  original employee/register. Atomic receipts, draft items and audits commit
  together. Concurrent retries create one order and acknowledgement. A failure in
  any line rolls back the entire draft. Stale edits return conflict rather than
  forcing a newer version. Captured timestamps are timezone-aware audit evidence,
  never invented payment timestamps. Sync never automatically prints or takes
  payment; kitchen sending and settlement remain explicit online operations.
- Pharmacy batch receiving, supplier returns and expired-lot disposal have an
  idempotent endpoint `/api/operations/batches/stock` and shared POS/Backoffice
  controls. Receiving uses the existing GRN service, including case breaking.
  Supplier returns/disposal use its stock-adjustment service with specific lot
  attribution, not a second stock deduction ledger. Lot amounts cannot go negative;
  existing expiry cannot silently change. Retries preserve request IDs. Required
  inventory and batch permissions are enforced. Returned customer goods still use
  the original financial refund workflow, not the supplier-return action.
- Profile changes retain visibility of existing restaurant/hospitality/wholesale
  documents and batch records, with existing permission and branch restrictions.
- New acknowledgement ledgers grant the runtime role SELECT/INSERT, not UPDATE
  or DELETE. No ownership or schema-CREATE privilege changes are introduced.

## Test evidence

Final complete backend suite: **332 passed, 122 permission subtests passed,
0 failures, 0 skips**, 71.70 seconds, including the missing-variant safety check.
Six existing warnings: one Starlette/httpx deprecation,
three Pydantic class-config deprecations, two pre-existing invalid Python escapes
in currency PDF assertions. Earlier targeted runs and the first full run passed
after a test-only SQLAlchemy expired-fixture refresh correction.

Frontend: all **24 test/lint/build commands** pass for POS and Backoffice. This
includes existing navigation, shifts, entitlement, credit, currencies, receipts,
offline quarantine, discounts, barcode, financial and native-printer source/JVM
guards, plus new offline-outbox/pricing checks. Existing hook-dependency and
preview Fast Refresh lint advisories and large-bundle build advisories remain.
Initial TypeScript failures (parameter properties under `erasableSyntaxOnly` and
nullable customer-level typing) were corrected before the passing builds.

Browser verification uses local Vite/Chromium, actual React components and only
synthetic adapters. HTTPS application requests are blocked. There are 86 PNGs,
124 page/viewport checks (24 employee, 32 printer, 40 business, 28 product), plus
offline draft creation at four widths and manager approval at three widths.
Widths: 1440, 820, 390 and 320 pixels. Browser Back and selected role restrictions
are checked. No horizontal page overflow was detected in these checked views.
An initial offline-panel test locator timeout was corrected and the unfinished
checks rerun; completed base captures were reused. This is not proof that every
button/form in the entire application has passed live end-to-end acceptance.

Printer simulations verify claim timeout causes no printing, concurrent duplicate
protection, uncertain jobs are not automatically retried, cashier isolation,
offline review preservation, escaping and 58/80 mm generation. They do not prove
physical paper delivery. Existing composite/variant, FEFO, retail, financial,
employee/branch/device and subscription regressions pass in the backend suite.

## Migrations and historical preservation

One linear graph:

`p5h_runtime_write_permissions → p7a_product_composites →
p7b_variant_pricing_tax → p7c_employee_roles_permissions →
p7d_printers_kitchen_jobs → p7e_business_orders_batches →
p7f_offline_order_receipts → p7g_batch_stock_operations`.

The last two are new Phase 7E additive migrations. They create acknowledgement
tables only; no historical association or financial value is backfilled.

The verified **16 October** production backup was used, not a fresh snapshot of
today's live database. Its SHA-256 matches the recorded deployment manifest:
`da9b191138ff052d48860359efc4ac850f5d5b805cdc2918e3b22e40db0c6e36`.
Source: `/root/apexretail-pos/backups/phase5-navigation-production/20261016T112917Z/apexretail_pos.dump`.

Restored clone: `apexretail_phase7e_production_clone_20261020`, starting at p5h.
PUBLIC/application CONNECT was revoked; the application account has no CONNECT.
No production service was contacted or stopped. Every pending migration was
applied separately, followed by full downgrade to p5h and forward recovery to
p7g. Across all nine stages, hashes/counts for the original columns of all 34
pre-existing tables (809 rows), currency-separated sale totals, stock totals,
historical shift-link counts and enforcement counts are unchanged. Added nullable/
defaulted fields are new schema, not historical financial rewrites. Raw business
rows are not exported into screenshots or evidence reports.

A separate empty synthetic p5h database passed the same complete migration
sequence. Nine populated synthetic fixture clones at p7g supported the regression
suite; the empty full-chain rehearsal alone is not a populated-data test.

Separate `apexretail_phase7e_guard` synthetic clone verifies populated batch
acknowledgements reject a full Alembic downgrade and the exact offline migration's
downgrade function rejects stored acknowledgements against real PostgreSQL.
All 58 tables, including version/history, remain unchanged after rejection.
The guard setup initially lacked a receipt and then had a synthetic SQL JSON
fixture syntax error; both were corrected before the passing guard evidence.
Downgrade after real operational writes is NOT an approved production recovery.
Use reviewed forward recovery and never restore an older DB over newer sales.

## Remaining release blockers and limitations

1. **Tip accounting policy requires owner decision:** tips owed to staff versus
   business revenue, and applicable tax/service-charge policy. The inherited
   service-product treatment is retained, not relabeled as a completed tip-liability
   ledger. Automatic percentage charges, staff payouts/liabilities and their
   dedicated reporting are not implemented. No historical accounts were rewritten.
2. Offline scope is unpaid drafts and version-checked edits, not offline restaurant
   settlement, offline KOT delivery or offline table transfers/merges. Server and
   client retry/retention tests pass, but full physical WebView lifecycle and
   cold-start-offline authorization/UI restoration are not certified. Stored drafts
   are retained; current authorization is needed before server operations. Complex
   conflicts require manual comparison with the current live order; no silent
   reassignment or force-version resolution exists.
3. Pharmacy variants do not have lot tracking. Customer refunds return stock through
   the original refund API and require subsequent inspected lot assignment; there
   is no completed return-inspection/quarantine/disposition workflow. Lot-specific
   transfers and stock-count reconciliation remain limited. Supplier returns are
   not supplier-credit financial documents; disposal records existing stock
   adjustments, not an automatic expense/payable accounting posting. Do not represent this as a full
   pharmaceutical or regulatory workflow.
4. The broad navigation/form requirement is only partially evidenced: existing
   regressions and targeted component/browser paths pass, but an exhaustive
   permission-aware, authenticated end-to-end matrix for every Save/Edit/Delete/
   Search/Filter/Print/Export action across the entire system is outstanding.
5. The restored backup is dated 16 October. A fresh read-only production backup
   rehearsal and current runtime-role checks are still required before release.
   Schema-owner migration execution passed locally; this is not a rehearsal of
   today's installed protected production deployment wrapper.
6. Legacy deployed API tests pass and new fields/routes are additive, but the
   installed Android APK was not rebuilt, installed or physically exercised.
   LAN printing requires the future approved native capability from Phase 7C;
   old APKs cannot gain it from a frontend/backend-only change.
7. Physical Bluetooth/USB/LAN printers, receipt/Z-report margins/cutters, scanner,
   WebView background/restart/network loss, and concurrent multi-terminal shop
   acceptance remain manual gates. Preview adapters do not replace these checks.
8. Existing operational list limits (100 orders/KDS, 1000 options), online-only
   kitchen state updates and legacy direct printing paths remain as documented in
   Phase 7C/7D. Quotations remain estimates repriced at conversion, not a new locked
   contractual quotation/tax engine. No hotel-booking or regulatory workflow added.

## Approval boundary

Review the synthetic screenshots and decide tip accounting policy before further
financial implementation. Do not deploy this candidate or run its migrations on
production. Do not build an APK. Production approval requires resolving the above
blockers and a separate controlled-release review.
