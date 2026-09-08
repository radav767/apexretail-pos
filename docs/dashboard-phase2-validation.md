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
- Responsive Dashboard filters/cards and mobile navigation. Filter requests
  ignore superseded responses, retain shop choices during loading, and avoid
  duplicate Dashboard requests and unrelated sales refreshes on filter changes.

## Results

- `bash backend/scripts/validate_dashboard_phase2.sh`: **79 tests passed**, no skips.
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
No production database or production dump was read. No deployment, service
restart, POS/APK rebuild, or publication was performed.

## Remaining limits

- Existing POS clients do not yet send explicit discount snapshots. Reports
  containing those or historical sales therefore show Discounts as unavailable.
  Client adoption is a follow-up; this change does not infer discounts from
  price overrides or label unknown discounts as zero.
- Browser interaction/end-to-end and visual mobile checks have not been run.
  UI coverage is component rendering; API coverage uses mocked auth actors and
  services, with real SQL covered separately by the temporary PostgreSQL test.
- Historical cost snapshots and tax semantics are inherited from Phase 1.
- Migration testing used a synthetic Phase 1 clone, not production data.
- Phase 2 is local and unpushed. Applying its migration and deployment require
  a separately authorized release.
