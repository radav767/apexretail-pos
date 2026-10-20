# Phase 7E completion review — PENDING ACCEPTANCE / NOT READY

Base: `d691e58438d7fd4683a41727cb7b332c6ff77b5c`.
Branch: `phase7e/integration-functional-completion`.
The exact resulting commit is in the protected review bundle's `release.json`.
This report updates, but does not erase, the previous stabilization evidence.

## Completed fixes

### Pharmacy and variant valuation

- A shared read-only stock-position query includes branch parent balances and
  variant balances as separate inventory dimensions. Company-wide legacy stock
  without a branch balance retains its existing fallback; it is not counted a
  second time when branch balances exist.
- Current variant cost/selling-price overrides use the same parent fallback as
  checkout. Inactive/archived variants with retained active balances are not
  silently removed from valuation under an active parent product.
- Inventory valuation totals, company/branch dashboard stock values, financial
  valuation rows and CSV now include variants. Rows retain variant names and
  optional variant IDs, and Backoffice table keys no longer collide for a
  parent's multiple variants in the same branch.
- Missing unit costs remain unavailable for nonzero stock, not fabricated zero
  costs. Zero parent stock with no parent cost no longer invalidates a fully
  known variant-stock total. Existing parent-only operational GRN/transfer
  balances are not overwritten with aggregated variant quantities.
- New read-only `GET /api/reports/batch-valuation/{company_id}` provides each
  lot's product, variant, branch, expiry, quantity, current unit cost and cost
  value. It uses existing valuation permissions and tenant/branch scoping.
  Amounts use the company's configured report precision without changing it.
- POS and Backoffice's shared Batches page exposes permission-gated valuation
  cards and CSV export. Lot values are **attribution of existing balances**,
  never additional inventory added to stock totals.
- This is explicitly **current recorded unit-cost valuation**. It does not
  invent historical batch acquisition costs, change FIFO/weighted-cost policy,
  write off expired stock automatically or rewrite historical sale costs.

### Three POS destinations

The hamburger menu and corresponding feature hubs now open dedicated pages:

| Destination | Existing authoritative action |
| --- | --- |
| Stock Transfers | Standard-stock `/inventory/transfers`, branch balances/history |
| Sales Reports | Filtered `/reports/sales-history` transaction view and CSV |
| Top Selling Products | Product-grouped persisted sales, revenue ordering and CSV |

The approved dark-green styling, existing browser Back/feature routing,
authentication and APIs remain. These pages do not replace working Backoffice
modules. Reports are backend-derived, not client-recalculated financial totals.

Transfer submission is saved locally before POST and guarded against same-view
double submission. An uncertain result survives reload and can be checked by
its original reference in source-branch history **without reposting**. A missing
recent record is not proof of failure: the request stays retained for manager
reconciliation. Only confirmed requests can be archived before a new transfer.
The confirmation query respects the existing history API's 500-record bound;
its real endpoint contract is covered in the PostgreSQL/ASGI test, not only the
synthetic browser adapter.
There is no claim of a new server-wide/cross-tab transfer idempotency protocol;
the unchanged legacy transfer API does not supply one. Lot/variant transfer
extensions are not silently invented by this navigation repair.

### Offline restaurant recovery and permissions

- Existing original-cashier/register-bound outboxes, immutable server receipts,
  original capture timestamps, atomic synchronization and conflict retention
  remain in place; full regression tests re-exercise these paths.
- Synchronization now explicitly rejects archived (`deleted`) employees even
  if a stale in-memory actor still has `active=True`. Normal authentication
  remains authoritative; no cached permission or PIN validation is bypassed.
- Existing drafts can be recovered by the current cashier after API-unavailable
  page startup. Network errors, malformed acknowledgements and version conflicts
  do not clear, reassign or force-sync queued commands.
- Current backend permission/tenant/branch checks remain authoritative. The
  new valuation/report routes and restricted transfer endpoint were exercised
  with denied employee actors, and cross-company report access was rejected.
- Browser checks verify denied focused pages render no forms/report data and
  make no component API requests. All 126 existing granular permission denial
  subtests pass. This is not certification of every role/page/action permutation.

## Final automated results

| Verification | Result |
| --- | --- |
| Complete backend suite, nine disposable PostgreSQL test databases | 374 passed; 126 subtests passed; 0 failures; 0 skips |
| Backend warnings | 6 existing deprecations; not suppressed |
| New completion integration tests | 9 passed, real PostgreSQL plus ASGI route checks |
| All POS/Backoffice `test:*`, lint and production build commands | 24/24 passed |
| Focused browser action/responsive checks | 16 recorded checks, all passed; denied-page checks also passed |
| Current screenshots | 16 actual React-component PNGs with synthetic data |
| Archived backup checksum/catalog | Verified |
| Restored isolated clone original-column content hashes | 34 tables / 809 archived rows unchanged |
| Production deployment/schema/data changes | None |
| APK build/install/app-data clearance | None |

The nine new integration tests cover variant-inclusive stock/dashboard/report
totals, CSV identities, lot costs after sale without historical mutation, cost
fallback/unavailability, company/branch/product filtering, restricted and
cross-company endpoints, archived-cashier synchronization denial, actual stock
transfer conservation/route denial, and the zero-parent-stock valuation edge.

The browser checks use the real focused report/transfer/valuation components and
synthetic Axios adapters at 1440, 820, 390 and 320 pixels. They verify form actions,
report/CSV requests, no horizontal overflow, and transfer timeout/reload/history
confirmation without a second POST. They are **not** physical Android tests or
complete authenticated end-to-end acceptance of the whole application shell.

Six backend warnings are one Starlette/httpx deprecation, three Pydantic Config
deprecations, and two existing PDF-test invalid escape literals. Lint passes
with existing Fast Refresh/hook dependency advisories and no errors.

`audit/acceptance-matrix.csv` separates automated backend results, frontend
command results, synthetic component actions and the source inventory of **778
controls/templates across 38 TSX files**. Unexecuted authenticated actions remain
PENDING, not PASS. A source connection or screenshot is not action completion.

## Printer and Android verification

Software evidence passes for printer station/routing and KOT lifecycle,
queue ownership, duplicate protection, uncertain-delivery retention, receipt
snapshot/reprint permissions, payload escaping and 58mm/80mm generation. The
frontend native-printer guard command validates four permitted private endpoints
and ten forbidden endpoints without making network connections. Native source
and printing code are unchanged from the preceding stabilization commit.

Actual environment observations:

- `adb devices -l`: server starts successfully; **no attached devices**.
- `lsusb`: only the Linux USB root hub; **no USB printer**.
- `/sys/class/bluetooth`: no adapter exposed.
- No dedicated safe LAN test-printer address was supplied or contacted.

| Required physical acceptance | Status |
| --- | --- |
| Bluetooth pairing, Android permission prompts and actual receipt output | PENDING |
| USB permission/receiver handling and physical print delivery | PENDING |
| LAN printer connection/status/failure recovery | PENDING |
| Kitchen/bar station routing and actual KOT paper output | PENDING |
| 58mm/80mm margins, glyphs, cutter, reprints and uncertain print handling | PENDING |
| Installed Android PIN/login, navigation, checkout/stock, restart and offline recovery | PENDING |

Source Android identity remains `cloud.apexpos.pos`, versionCode 6/versionName
1.4.0; no native configuration, permissions, signing identity or bundled native
assets changed. Existing sale/shift/API compatibility regressions pass. This is
software-level compatibility evidence, **not** certification of an installed
APK's runtime behavior or certificate. No APK was built, signed or installed.

## Database and backup safety

There are **no new migrations in this change set**. The existing reviewed head
remains `p7j_variant_batches`; deployments starting at p5h would still require
the previously reviewed complete p7a–p7j chain. No migration was run on production.

The known verified October 16 archived backup still matches SHA-256:
`da9b191138ff052d48860359efc4ac850f5d5b805cdc2918e3b22e40db0c6e36`.
Its custom-format catalog is readable. Its preceding fresh full restore and
12-stage upgrade/downgrade/forward-recovery rehearsal remain recorded; the
migration files are unchanged, so that expensive rehearsal was not repeated.

A new **read-only transaction** rechecked every original-column content hash
on `apexretail_phase7e_stabilization_clone_20261020`: all 34 original tables and
809 archived rows match their baseline. The clone is at p7j with application
CONNECT disabled. This is an archived-data preservation check, not evidence that
today's live production matches that October 16 snapshot.

No production connection, financial write, schema/ownership/privilege change,
database reset, rate/currency-setting change, mandatory-enforcement activation,
queue deletion or frontend/backend deployment occurred. Isolated test fixtures
are the only business transactions generated. Prior evidence/builds/APKs remain.

## Remaining acceptance gates and limitations

1. **PENDING:** authenticated action-by-action acceptance of all legacy forms,
   searches, filters, imports/exports and role/branch/device permutations. The
   matrix does not relabel the source inventory as tested runtime coverage.
2. **PENDING:** all real-device/printer tests above. No physical test has been
   claimed successful merely because a browser, queue or source test passed.
3. **PENDING:** current-production backup freshness/integrity, live-version/data
   compatibility and protected runner/runtime-role review. Production was not
   inspected or modified during this task.
4. Supported restaurant offline scope remains unpaid draft/versioned-edit
   recovery. New draft creation after cold start without a loaded profile,
   offline payment/KOT dispatch, merge and forced conflict resolution are not
   advertised as supported. Secure cashier-bound retention and duplicate
   prevention do not imply those separate workflows have been implemented.
5. Existing broader Phase 7E limitations remain: advanced lot transfers/counts,
   supplier-credit/automated disposal-expense documents, accountant/legal tip
   acceptance and gateway/payroll automation. Existing modules were not removed
   to hide these limitations.

**Production readiness: PENDING / NOT READY (NO-GO for deployment).**
The reported valuation omissions and three POS destinations are fixed and their
targeted software checks pass. Phase 7E must not be marked READY until every
required remaining acceptance gate has passed. Obtain separate authorization
before deployment or a production APK build.
