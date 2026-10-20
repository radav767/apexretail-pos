# Phase 7 software completion — 20 October 2026

Continued from `753d9ea9cf4fc8e52ce8f0b13528766824a6c97b` on the existing
`phase7g/android-shift-acceptance` development branch/worktree. No production
deployment, production database access, new staging environment, database reset,
APK build, or physical-device test was performed.

## Implemented and verified

- POS and Backoffice transfers explicitly select a variant, show its SKU and
  source quantity, and require server variant-transfer capability. Requests and
  retries retain the original variant and request UUID. Backend movements use
  existing balances and FEFO lot allocation, preserving lot codes and expiry.
  Source-branch permissions remain enforced; a scoped destination list fixes
  branch-restricted staff being unable to choose an allowed transfer destination.
- Both applications use the same stock-count component. Physical positions
  distinguish variants from retained parent stock and show selected lots and
  expiry dates. Counts carry the original expected quantity and an optional
  idempotency UUID; stale snapshots fail rather than overwrite subsequent stock.
  Original requests, acknowledgements and explicitly rejected counts are retained.
  Selected-lot counting preserves attribution; generic counting cannot change a
  lot-tracked position. Inactive retained variants can be counted explicitly.
- Metadata-only variant edits now return the actual branch quantity instead of
  the response schema's misleading zero default. Invalid branch references are
  rejected before saving metadata.
- The existing unpaid restaurant outbox now supports explicit kitchen-dispatch
  and KDS-status intents. Original employee, register, timestamp and version/status
  are retained. Current server permissions are checked on synchronization.
  Dispatch/status mutations and their receipts commit atomically. Retries recover
  the original receipt, not a replacement order or ticket.
- Added read-only conflict review and explicit, reasoned acceptance of the
  current server state. Resolution appends an immutable receipt and audit event,
  retains the original command, and never silently forces its stale mutation.
- KDS caches are cashier/device scoped and contain no cached authorization
  grants. Cached views are labelled unconfirmed; current permissions remain
  necessary. Offline cold-start recovery retains commands but does not grant new
  operational permissions from cached kitchen data.
- **Offline restaurant payments remain disabled.** Saving or synchronizing an
  unpaid order/KOT/KDS intent does not charge, deduct stock, or claim a printer
  physically printed. Existing financial sales queues are untouched.
- The real built POS stock-count page exposed a duplicate-React runtime crash;
  POS now deduplicates React for shared Backoffice components, matching the
  existing Backoffice build policy.
- Hardened the existing acceptance asset publisher: it refuses production API
  targets or missing loopback HTTPS targeting, and requires the Backoffice base
  path. This is a guard on the existing environment, not new infrastructure.

## Verification results

| Verification | Final result | Scope |
| --- | --- | --- |
| Complete backend regression suite | 406 passed, 146 subtests passed; no failures/skips | Existing rollback-only PostgreSQL test databases |
| POS/Backoffice tests, lint and builds | All 24 commands passed | Existing npm scripts; optimized test builds |
| Authenticated HTTPS operation assertions | 36 passed | Existing isolated tenant/database, real API and runtime application role |
| Real authenticated UI actions | 24 passed | Real POS/Backoffice, not mock adapters |
| Authenticated navigation/responsive suite | 79 passed; no API errors or external requests | Existing acceptance environment |
| Synthetic component action suite | 44 passed | Explicitly mocked adapters, distinct from the real API/UI checks |
| Staging publication guard | Passed including 4 rejected unsafe API targets and wrong Backoffice base | Pure artifact tests; no service/database access |
| Printer/Android checks | Existing source/transport-contract checks passed | Not physical printing, installation or APK build |

Real UI actions included category create/edit/delete in both clients, persisted
records after reload/PIN reauthentication, acknowledged stock counts after
restart, variant metadata edits, and 320/390/820/1440px stock-count layouts.
Restaurant actions included actual offline draft saving, reconnect/reload
recovery, unchanged original timestamps and identity, KOT duplicate protection,
KDS synchronization, and explicit UI conflict resolution without a forced state
overwrite. Offline payment controls stayed disabled.

Actual HTTPS checks additionally covered variant transfers/count retries,
selected-lot receiving/counting/supplier returns/disposal, negative-lot protection,
cross-company rejection, online variant cash sale retry, exactly-once deduction,
Backoffice sales history, zero-float opening, closing reconciliation, immutable
PDF and 58/80mm report generation. An earlier run stopped on an existing open
test shift; that shift was preserved and the run completed in the other existing
test tenant. Synthetic records from partial runs were retained, not reset.

Six backend warnings remain: Starlette/httpx deprecation, three class-based
Pydantic configuration deprecations, and two existing test escape-sequence
deprecations. Lint has 2 existing POS and 8 Backoffice warnings, with no errors.
Builds retain the existing advisory about chunks exceeding 500 kB.

## Action coverage and limits

| Module | Verified action evidence | Outstanding acceptance |
| --- | --- | --- |
| Products/categories | Real authenticated CRUD, variant edit; component create/edit/archive/restore and dependent-delete rejection; backend catalog/composite/import/security regressions | Owner workflow acceptance across their catalog |
| Variants/composites/pricing | Explicit variant transfer/count/sale and retry; existing component-level stock, refunds and pricing regressions | Physical barcode scanner/scale where used |
| Inventory/pharmacy | Real batch receiving, expiry/code identity, count, supplier return, disposal and valuation response; variant lot/cost/return-inspection regressions | Physical counts and scanner acceptance |
| Employees/permissions | Actual password/PIN/device authentication, tenant rejection; backend role/branch/device/manager-approval restrictions | Representative staff/role acceptance, not just owner UI |
| Shifts/sales/credit/refunds | Actual cashier-bound sale, retry, stock, history, close, PDF; complete financial/credit/refund/shift regressions | Operator cash-drawer reconciliation |
| Restaurant/KDS/KOT | Actual offline/recovery/duplicate/conflict UI and HTTPS actions; atomic failure-injection regressions | Multi-device service-floor acceptance and physical KOT delivery |
| Reports/navigation/settings | 79 authenticated navigation/responsive assertions; report/calculation/security regressions and actual sales-history/PDF checks | Final business-user acceptance |
| Printers/Android | Automated transport, security, source and backwards-compatible API regression checks | Real Android app lifecycle/storage, Bluetooth, USB, LAN, receipt auto-print, reprint, 58/80mm and kitchen routing |

Navigation passes are not represented as proof of every legacy form action.
Component-adapter passes are not represented as authenticated backend tests.
Physical hardware and installed Android compatibility have **not** been marked
passed. No known failing software check remains in the final runs; manual gates
below still prevent an unconditional production GO.

## Migration, backup and recovery

No migration files changed from the verified starting commit; no new migration
is required by these fixes. Existing Phase 7 head remains `p7j_variant_batches`.
The previously completed rehearsal upgraded p7a through p7j, downgraded to
`p5h_runtime_write_permissions`, then recovered forward to p7j on disposable
databases. That expensive rehearsal was not repeated because its inputs did not
change.

Reverified the archived 16 October production backup:

`backups/phase5-navigation-production/20261016T112917Z/apexretail_pos.dump`

SHA-256: `da9b191138ff052d48860359efc4ac850f5d5b805cdc2918e3b22e40db0c6e36`.

Archive catalog is readable. Its existing restored clone
`apexretail_phase7e_stabilization_clone_20261020` remains at p7j with application
CONNECT disabled. All original-column hashes and counts match: **34 historical
tables, 809 rows**. This is archived-backup preservation evidence, **not** a
claim about current production freshness or current production row totals.

Before deployment: obtain explicit authorization, verify live revision/current
release, create/restore-verify a fresh consistent backup, compare current
historical hashes/totals, and rehearse any changed production migration baseline
through the protected schema-owner runner. Preserve previous static assets and
configuration. Never downgrade populated new operational tables casually or
restore an older database over newer transactions; after new financial writes,
use reviewed forward recovery. No recovery action was run on production.

## Evidence and decision

Durable evidence:
`/root/apexretail-pos/artifacts/phase7-software-completion-20261020/`.
Contains backend JUnit/logs, all frontend command logs, authenticated action
results, navigation results, synthetic component results, screenshots, archived
backup/hash/rehearsal evidence and a SHA-256 manifest. It contains no passwords,
bearer tokens, signing keys or private acceptance-account files.

**Software checks: PASS for the tested scope. Production release: PENDING / no
deployment authorized.** Physical printer/Android acceptance, representative
operator sign-off and fresh production backup/migration preflight remain gates.
No production changes, mandatory-enforcement changes, or APK rebuild occurred.

Phase 8 can proceed as development on this same project after owner review:
reuse and verify existing subscription/licensing code before adding billing;
retain tenant isolation, signed offline entitlement rules, idempotent payment
events and financial audit trails. ZIMRA fiscalisation remains a later milestone.
