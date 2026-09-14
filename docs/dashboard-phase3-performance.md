# Dashboard Phase 3 performance gate

Status: corrective release gate for the frozen Phase 3 feature scope.

## Decision

The isolated representative benchmark must complete every measured dashboard
query in no more than **2,000 ms of PostgreSQL execution time**. The gate applies
individually to summary, daily trend, and top-products queries on the standard
25,000-sale/75,000-item fixture. Fixture creation, application serialization,
network time, and browser rendering are reported separately and are not included
in this database-query ceiling.

Two seconds is a conservative upper bound for an interactive Backoffice request
on the validation host. It allows substantial host variance while rejecting a
plan that would make an operator wait minutes. This release gate is not a
production percentile SLO. Production telemetry and a separately approved SLO
are still required before using p95 or p99 claims.

## Baseline incident and diagnosis

The 2026-09-14 release-candidate run at commit
`8bb11f2ef2f0fd8c8e8dcf59916b60e26ddc1431` recorded:

| Query | PostgreSQL execution |
| --- | ---: |
| Summary | 299,782.484 ms |
| Daily trend | 290,577.014 ms |
| Top products | 107.267 ms |

The benchmark restored a small production snapshot containing 57 sales and 71
sale items, then inserted 25,000 sales and 75,000 items inside the transaction
that would later be rolled back. PostgreSQL statistics continued to describe the
57/71-row database. Summary and trend therefore received a plan based on badly
underestimated cardinalities. This was a measurement-fixture defect, not an
accounting discrepancy.

The corrective benchmark runs `ANALYZE sales, sale_items` after fixture creation
and before `EXPLAIN ANALYZE`. The statistics and fixture rows are scoped to the
same isolated transaction and the transaction is rolled back. The script now
prints success only after rollback completes.

## Corrected evidence

The first targeted rerun used the same retained isolated clone, same application
query text, same dates, and same 25,000/75,000 fixture. It added no index and
changed no accounting logic:

| Query | Before | Corrected | Corrected plan |
| --- | ---: | ---: | --- |
| Summary | 299,782.484 ms | 144.822 ms | one-pass scans and hash joins |
| Daily trend | 290,577.014 ms | 147.134 ms | one-pass scans, hash joins, aggregate |
| Top products | 107.267 ms | 89.077 ms | one-pass scans, hash join, aggregate/limit |

The corrected plans scanned 25,000 eligible sales once and 75,071 total sale
items once. The item-cost join returned 75,000 rows with one actual loop. Summary
and trend no longer used the pathological plan implied by stale statistics.

## Index decision

No Phase 3 index is introduced by this correction. On this representative
fixture the selected tenant/date range contains nearly every synthetic row, so
sequential scans plus hash joins are appropriate and finish far below the gate.
Adding an index without a selective before/after case would add migration,
write-amplification, and rollback surface without evidence of benefit.

If later evidence covers selective tenant, shop, or short-date queries at larger
scale, evaluate candidate indexes separately. Any index proposal must include:

- identical accounting results before and after;
- `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` from the same isolated fixture;
- index size and insert/update overhead;
- concurrent/additive migration and downgrade behavior; and
- proof that the planner uses it for the intended selective workload.

## Repeatability and failure behavior

The benchmark:

- refuses database names outside the Phase 2/3 test prefixes;
- records the fixture size, threshold, pass/fail result, and diagnostic plan
  nodes;
- fails nonzero when any measured query exceeds 2,000 ms;
- rolls back fixture records even when measurement or threshold evaluation
  fails; and
- must be followed by a zero-fixture-row check during release-candidate
  validation.

Changing the threshold, fixture, query population, timezone, or accounting
contract requires review and invalidates direct comparison with this baseline.
