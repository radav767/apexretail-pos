# Phase 7E stabilization — PARTIAL / NO-GO

Development continues from `413eebc368ed1b50ff6e4df5ece65fa148a002cb` on
`phase7e/integration-functional-completion`, in `/tmp/apexpos-phase7e`.
This report supersedes the continuation report for the changes and verification
below. The exact resulting commit is recorded in the release evidence manifest.

**This is not a complete functional acceptance or a production release approval.**
The regression commands pass, but important software and manual gates remain.
No production connection, deployment, production schema/data write, APK build,
installation, queue clearance, currency change or enforcement activation occurred.

## Implemented and fixed in this stabilization

### Variant-specific pharmacy lots

- Explicit optional variant identity on batch assignment and stock operations;
  separate uniqueness for parent lots and variant lots. Two strengths/sizes may
  have the same physical batch code without sharing their inventory.
- Receive, case-breaking, selected-lot supplier return and disposal reuse
  `InventoryService` and the existing movement ledger. Variant balance access
  reuses the sale repository's authoritative balance implementation; there is
  no second stock deduction engine.
- Sales allocate their existing variant movement through the common FEFO hook.
  Expired lots, insufficient quantities and negative removals fail atomically.
- Returned stock is held against its **original immutable refund movement's**
  variant. Inspection allocates an already restored refund, not another stock
  receipt. Disposal makes one existing-ledger removal and no second refund.
- Generic variant stock editing cannot bypass lot accounting/return inspection.
  Metadata and price editing, and ordinary non-lot variant behavior, remain.
- Original parent balances/lots remain untouched; no historical variant links
  are inferred. Existing parent lots must not be consumed by new variant sales.
- POS and Backoffice share variant selection, variant-labelled return review,
  batch history and variant-labelled CSV export. Existing nonvariant queued
  stock requests retain their pre-migration payload hash format.
- Batch UI retries retain the original request and variant across reloads and
  reject malformed HTTP-200 acknowledgements. An in-flight ref blocks same-view
  double submission. This is not a claim of a global cross-tab lock.

### Offline restaurant recovery

- When the business profile API is unavailable after reopening the page, the
  existing authenticated POS shell can expose **only its current cashier's**
  saved unpaid-order outbox. The identity is passed from the current cashier,
  not invented from a different cashier's saved draft.
- Recovery mode cannot create new drafts, perform payments, dispatch KOTs or
  trust a cached unsigned permission profile. Reconnection probes/submissions
  continue through current backend authentication, branch/device permissions,
  immutable request hashes and version checks.
- Original timestamps/payloads, unresolved conflicts and acknowledged receipts
  remain stored. No draft, financial queue or local session data is deleted.
- Browser tests verify API-unavailable startup, page close/reopen, conflict
  retention, disconnected controls, original-timestamp server-confirmation
  recovery and cashier switching. This is component/browser evidence, not
  physical Android cold-start/offline PIN certification.

### Navigation

Four supported POS submenu entries now select the existing dedicated feature
instead of dropping the cashier onto the generic module hub:

- Transaction History → `transaction-history`.
- Goods Received → `goods-received`.
- Stock Adjustments → `stock-adjustments`.
- Sales Summary → `sales-summary`.

The approved dark-green design, existing routes, permissions and financial
actions are retained. Unsupported/misleading remaining destinations are listed
as blockers below; they have not been represented as working features.

## Functional audit and acceptance evidence

`audit/acceptance-matrix.csv` contains Feature, Action, Test result, Remaining
limitation, verification type and evidence for each entry. It combines:

1. The 365 actual backend test cases and their machine-readable results.
2. All 24 frontend regression/lint/build command results.
3. Recorded responsive/component browser checks using actual React components
   and synthetic API adapters.
4. A source inventory of 762 controls/templates across 36 POS/Backoffice TSX
   files, including buttons, forms, links, inputs, selectors and custom action
   props. Dynamic templates retain their handlers and source locations.
5. Explicit unsupported, unverified and manual release gates.

**A source-connected control is not a passed end-to-end action.** Those inventory
entries are deliberately `NOT VERIFIED end-to-end`. A test's PASS applies only
to the behavior exercised by that test. Dynamic grids still need per-item,
authenticated browser acceptance. Search/input event coverage is not proof of a
successful backend Create/Edit/Delete/Save transaction.

| Module | Existing automated evidence | Remaining action acceptance |
| --- | --- | --- |
| Products/categories | Category/composite unit/integration cases, CRUD endpoint/permission guards, responsive tools | All real authenticated category/product CRUD and dependency-error UI paths |
| Variants/price levels | Variant pricing/tax/stock/retry tests; new lot tests; customer tier and quotation conversion tests | All variant/price-level edit/archive forms; legacy valuation gap below |
| Images/import/export/barcodes | CSV/XLSX parsing/validation, spoofed image/tenant rejection, barcode tests and tool screens | Real camera/gallery/scanner, valid large uploads, all CSV/XLSX commit/error/export paths |
| Inventory | Existing transfer/count/adjustment/report tests plus lot case-breaking/returns/disposal | Lot-aware transfer/count reconciliation and every Backoffice form action |
| Sales/refunds/history | Sale/discount/currency/tax/refund/duplicate/session regressions | Full authenticated POS → history → Backoffice UI journey and timeout acceptance |
| Credit/customers/expenses | Existing backend and frontend regression commands | Every CRUD/search/filter/export and manager approval combination |
| Employees/roles/permissions | PostgreSQL employee/manager tests; 126 permission subtests; employee screens and manager dialog browser checks | Every role/branch/device assignment and disabled-session browser path |
| Shifts/Z reports/tips | Shift isolation/reconciliation/currency/PDF tests, immutable tip policies/allocations/reversals/payouts and shift snapshots | Physical drawer/printer and full business/accountant tip acceptance |
| Restaurant/hospitality | Order lifecycle, quantity splits, settlement atomicity/idempotency, guest credit and reports | Full floor/waiter/room browser actions, offline unsupported operations below |
| Kitchen/printing | Queue ownership/retry/duplicate protection, KDS/bar roles and source/JVM guards | Physical routing/delivery/paper/cutter and installed Android client |
| Pharmacy | 14 new real-PostgreSQL variant-lot tests plus existing FEFO/inspection/hold tests | Lot transfers/counts; all saleable-versus-held presentation/report paths |
| Reports/analytics | Existing persisted-sales, discounts/refunds/profit/currency report regressions | Variant valuation defect below; all filters/drilldowns/export UI combinations |
| Settings/devices/printers | Existing registration/device/entitlement and permission suites, responsive printer/settings checks | All settings Save/restart flows and real hardware/device restrictions |

This audit does **not** certify every feature as complete. Read the CSV together
with its evidence type and the release gates, not as an all-green checklist.

## Verification results

- Final backend suite: **365 passed, 126 subtests passed, 0 failed, 0 skipped**.
  Nine isolated PostgreSQL regression databases; real-PostgreSQL, API, unit and
  repository-double tests retain their original distinctions.
- Backend warnings: six — one Starlette/httpx deprecation, three Pydantic
  class-based Config deprecations, two invalid-escape deprecations in existing
  PDF currency test literals. These were not suppressed.
- New variant-lot suite: **14 passed**. Covers separate lots/balances, receive
  replay, sale retry, exact deductions, returns/inspection/disposal, case
  breaking, held stock, permissions/identity, historical parent preservation,
  expiry, downgrade refusal, generic editor guard, negatives, request-identity
  reuse and audit/movement attribution.
- Frontend: **24/24 commands passed**, including all available POS/Backoffice
  `test:*` scripts, both lint commands and both production builds.
- Lint has existing advisory Fast Refresh/hook dependency warnings; no errors.
  Passing source/static tests are not presented as authenticated UI E2E.
- Fresh synthetic captures: 86 broad module PNGs, 12 tips/returns PNGs, eight
  stabilization PNGs. Recorded checks cover widths 1440, 820, 390 and 320;
  targeted browser actions include original-request stock retries, malformed
  acknowledgements, draft recovery/conflicts, tip settings/save/report/CSV,
  transfer-recording retries and return inspection.
- The 106 PNGs are actual React interfaces with synthetic data. They are not
  production screenshots, mockups or Android hardware screenshots.
- Initial new test attempts failed because a fixture field shadowed a helper
  and because post-rollback ORM assertions needed explicit async refresh. A
  browser test initially used an incorrect select-label locator. Those test
  harness issues were corrected; the final complete runs above have no failures.

## Migration readiness and historical preservation

New additive migration: `p7j_variant_batches`, descending from
`p7i_pharmacy_return_holds`. It adds nullable `product_batches.variant_id`, a
foreign key and parent/variant partial unique indexes. It does not alter
deployed migrations, assign old lots, rewrite financial records or change
application/schema ownership/privileges. Downgrade refuses once variant lots
exist; operational data requires reviewed forward recovery.

Full chain:

`p5h → p7a → p7b → p7c → p7d → p7e → p7f → p7g → p7h → p7i → p7j`.

The known verified **October 16 archived production backup**, SHA-256
`da9b191138ff052d48860359efc4ac850f5d5b805cdc2918e3b22e40db0c6e36`,
was restored into a fresh isolated database:
`apexretail_phase7e_stabilization_clone_20261020`.
PUBLIC/application CONNECT was revoked. No live production connection was used.

That restore and a separate fresh empty database each passed 12 stages: ten
individual Phase 7 upgrades, downgrade to p5h, then forward upgrade to p7j.
All 34 original tables/809 archived rows retained their original-column content
hashes and row counts at every stage. Currency-separated sales totals, inventory
totals, historical shift links and enforcement flags were unchanged. Old column
projections distinguish additive defaults from rewritten historical values.
Currency configuration is covered by the original table hashes.

Populated variant-lot downgrade refusal was tested against real PostgreSQL using
the exact migration downgrade function, not a production wrapper. Existing tip
and held-return downgrade guards remain covered by the regression suite. Do
not confuse the empty/archive full-chain rehearsal with certification of the
current protected production migration runner or an arbitrary populated rollback.

## Production and Android compatibility

- No API contract, sale/stock deduction engine, authentication/PIN/device rule,
  receipt formatter, production service or production configuration was replaced.
  New batch fields are optional; existing sale/shift/offline contracts pass the
  existing compatibility/regression suites.
- The production API default remains `https://api.apexpos.cloud/api`; no test
  server or preview adapter is a production entry point.
- Native Android files are unchanged from `413eebc`; source application ID
  `cloud.apexpos.pos`, versionCode 6/versionName 1.4.0 are unchanged. No signing
  credentials were read or changed and no APK was rebuilt or installed.
- Printer source/JVM compatibility checks pass. Actual installed APK/WebView
  compatibility, hardware permissions, restart and queued transaction recovery
  remain unverified physically. Older clients do not gain these new screens
  without a separately approved future client build.
- Mandatory shift enforcement was not enabled. Isolated baseline flags remained
  unchanged; no claim is made about a newly queried live production setting.

## Remaining blockers — do not deploy

1. **Exhaustive functional acceptance is incomplete.** Every source control has
   been inventoried, not every action executed. The 762 control/template rows
   must not be relabelled PASS based on builds or visual screenshots.
2. **Variant inventory valuation is incomplete.** Existing legacy valuation and
   financial inventory report queries read parent `products`/
   `inventory_balances`, omitting the separate `variant_inventory_balances`
   quantities/costs. Sale cost snapshots can pass while current valuation is
   incomplete. Reconcile this across reports/dashboards with dedicated financial
   tests before claiming variant/pharmacy release readiness. No incorrect total
   was silently added to history in this work.
3. POS menu entries **Stock Transfers, Sales Reports and Top Selling Products**
   still lack matching dedicated POS feature destinations and open a hub.
   Working Backoffice modules were preserved; these POS destinations still need
   implementation/reconciliation and action tests, not another cosmetic label.
4. Cold-start-offline **new** restaurant draft creation remains blocked until a
   current profile/permissions load. Recovery of existing cashier-bound drafts
   works in browser tests. Offline payment, KOT dispatch, table transfer and
   merge remain unsupported/fail-closed. Conflict retention/probing is not an
   authorized merge or force-version resolution workflow.
5. Lot-level transfers/counting and saleable-versus-held totals across legacy
   clients need completion/acceptance. Supplier-credit documents, automated
   disposal-expense posting and regulated prescription workflows are not added.
6. Tips/service-charge legal/accounting acceptance, payment-provider/payroll
   automation and receipt/customer tip slip behavior remain as documented in
   `PHASE7E-TIPS-AND-RECOVERY.md`. No automatic percentage service charge or new
   tip-specific manager-approval token is claimed.
7. Physical Android cold restart/PIN/network recovery, camera/scanners,
   Bluetooth/USB/LAN printers, 58mm/80mm paper margins, cutters, KOT routing and
   uncertain print recovery require real devices. Browser/JVM checks are not
   substitutes for these manual gates.
8. A current production backup, protected migration-runner/runtime-role review,
   coordinated rollout/old-client compatibility and forward-recovery review
   remain required. The October 16 backup is not today's live production state.

**Recommendation: NO-GO.** This stabilization delivers verified improvements,
not completion of every requested release gate. Keep production unchanged and
review the remaining software work and manual acceptance requirements before
any separate deployment or APK authorization.
