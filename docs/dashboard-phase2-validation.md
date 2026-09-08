# Dashboard Phase 2 local validation

Validated on 2026-09-08 on `phase2/dashboard`, resumed from `e945de8`.
The retained stash was inspected, not reapplied or removed:
`4bf05469530c72b04d5db1342e2ffd55b5b7ec53`.

## Implemented behavior

- Authenticated `/api/dashboard/summary-v2/{company_id}` with company isolation,
  reports permission, shop selection, and Africa/Harare date boundaries.
- Today, yesterday, last seven days, previous calendar month, and custom ranges
  of at most 366 inclusive days.
- Separate sale and item aggregates avoid multiplying revenue by item count.
  Gross sales sums original sale totals, including originals later refunded;
  refunds sum reversal transactions on their own transaction dates. Net sales
  is gross sales less refunds; gross profit is net sales less signed item cost.
  Totals retain the existing sale tax semantics.
- Additive `d3phase2discount` migration adds nullable `sales.discount_amount`,
  with no default or historical backfill. Explicit snapshots must match the
  reduction from submitted unit-price totals to line totals. Positive snapshots
  require employee discount permission. Existing clients may omit the field.
- POS checkout now sends explicit zero or positive discount snapshots, including
  line and sale discounts allocated in whole cents before tax. Offline queue/retry
  preserves omitted/null legacy snapshots and explicit values. Refunds use paid
  line totals and preserve the original discount snapshot. Checkout validates
  numeric precision, limits, consistency, and discount permissions.
- Responsive Dashboard filters/cards and mobile navigation. Filter requests
  ignore superseded responses, retain shop choices during loading, and avoid
  duplicate Dashboard requests and unrelated sales refreshes on filter changes.

## Results

- `bash backend/scripts/validate_dashboard_phase2.sh`: **82 tests passed**, no skips.
  Includes API authorization/validation, date ranges, aggregate repository,
  discount snapshot persistence, and PostgreSQL aggregate integration coverage.
- Migration paths passed: empty database to head; synthetic Phase 1 baseline
  cloned to a temporary database then upgraded; Phase 2 downgrade/re-upgrade.
  Historical discount remained null and total unchanged. Integration inserts
  rolled back, leaving no sales or companies in the fresh database.
- `cd backoffice && npm run test:dashboard`: **3 tests passed**.
  Covers rendered ranges, selected shop, metrics, unavailable values, and
  shop choices while loading. These are server-rendered component tests.
- `npm run lint`: passed with **12 existing warnings** in other pages;
  no Dashboard warnings.
- `npm run build`: TypeScript and Vite passed.
- `git diff --check`: passed.

The earlier API-test hang reproduced only in the sandbox's thread execution;
mocked API tests and the full suite passed outside it. No application routing
change was needed. PostgreSQL validation used a newly initialized, socket-only
cluster under `/tmp`, synthetic records only, and stopped the cluster afterward.
No production database or production dump was read. No deployment, production
service restart, APK rebuild, or publication was performed. Only isolated temporary test services were started and stopped.

## Remaining limits

- Historical sales and older deployed POS clients may omit discount snapshots;
  those report ranges correctly show Discounts as unavailable. The updated POS
  source sends snapshots, but no APK was rebuilt or released.
- Mobile checks used Chromium viewport emulation, not physical Android hardware.
  POS discount calculation and offline synchronization were tested programmatically;
  a physical-device checkout/printing test remains outside this validation.
- Historical cost snapshots and tax semantics are inherited from Phase 1.
- Migration testing used a synthetic Phase 1 clone, not production data.
- Phase 2 is local and unpushed. Applying its migration and deployment require
  a separately authorized release.

## Final review and applicability (2026-09-08)

Reviewed the complete branch diff from `e945de8`, including the committed Dashboard
work in `094e8ed` and the remaining checkout changes. Scope is Dashboard API/UI,
nullable discount snapshot model/migration, POS discount capture and offline/receipt
propagation, associated checkout/refund validation, tests, and this report.
No deployment, production configuration, generated assets, APK, or dependency
lockfile changes are included. The refund status fix evaluates awaited refund
quantities as a list rather than passing an async generator to `all()`.

The saved isolated validation run finished at 21:10:39 UTC, after the final backend
service edit at 21:10:10 UTC and schema/test edits before it: **82 backend tests
passed, no skips**. It also passed fresh-to-head, synthetic Phase 1 clone upgrade,
downgrade/re-upgrade, historical null/total preservation, and integration rollback.
Backend code, migration files, and backend tests have not changed since that run;
these results remain applicable and were not unnecessarily repeated.

Final frontend verification:

- POS `npm run test:discounts`: passed discount arithmetic/allocation/validation
  and real queue/sync code exercised through an in-memory SQLite bridge, including
  duplicate enqueue, failed network retry, concurrent sync, omitted/null/zero and
  positive snapshots.
- POS `tsc -b --pretty false`: passed; no POS asset publication or APK build.
- Review corrected discount display/edit targeting for repeated weighted-product
  rows to use cart position, then reran POS discount tests and TypeScript checking.
- Backoffice `npm run test:dashboard`: 3 passed.
- Backoffice `npm run lint`: passed, 12 existing warnings in unrelated pages.
- Backoffice `npm run build`: passed. Dashboard sources were unchanged after the
  authenticated browser run, so those browser results remain applicable.

## Authenticated browser validation

Completed against the preserved synthetic fixture on 2026-09-08. Backoffice ran
on `127.0.0.1:5173`, API on `127.0.0.1:8765`, and PostgreSQL used only its temporary
Unix socket. A temporary Vite transform replaced the hardcoded API URL in memory
with a local proxy; repository API configuration was unchanged. Browser routing
blocked non-loopback requests; no external application requests were recorded.

Passed:

- Owner login through the real authentication endpoint and six Dashboard cards.
- All-shop gross sales `$2469.00`; Harare shop gross sales `$1234.50` and explicit
  discounts `$5.50`.
- All five reporting periods returned successful responses.
- Reversed custom dates displayed validation and cleared stale metric cards.
- Desktop screenshot and 390px/320px mobile layouts; no horizontal overflow;
  mobile menu navigation closed the menu after selection.
- Authentication persisted through reload.
- Authenticated employee without reports permission received HTTP 403 and no
  metric cards.
- No browser runtime errors or external application requests.

Chromium required two libraries extracted only under `/tmp`; no system packages
were installed. A test selector was corrected to account for a CSS icon in the
Dashboard navigation button's accessible name; the complete script then passed.

## Temporary resource cleanup

Validated exact cluster paths `/tmp/apex-phase2-validation-Y0XRke`,
`/tmp/apex-phase2-validation-JaDCeR`, `/tmp/apex-phase2-validation-Mf9VCm`, and
`/tmp/apex-phase2-validation-pq9JBf`. Each was a socket-only PostgreSQL 14 test
cluster containing only `apexretail_phase2_test_baseline`,
`apexretail_phase2_test_clone`, `apexretail_phase2_test_fresh`, and the cluster's
standard administrative/template databases. No `apexretail_pos` database
was targeted or accessed. Each cluster was stopped before its exact directory
was removed. Temporary browser scripts, synthetic credentials, screenshots,
results JSON, and extracted browser libraries were removed by explicit path;
the browser results are retained above. Test ports and processes were checked
again after cleanup. The retained stash remains
`4bf05469530c72b04d5db1342e2ffd55b5b7ec53`.
