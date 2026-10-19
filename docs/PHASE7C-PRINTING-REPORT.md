# Phase 7C — Printer management and kitchen tickets

Status: development implementation verified; NOT deployed. Owner review and hardware acceptance are required. No APK was assembled, signed or installed.

## Existing implementation audit

- Android already supported paired Bluetooth classic ESC/POS, USB permission/discovery and system print services. Existing Bluetooth permission and non-exported USB receiver guards are preserved.
- Chrome/desktop already supported OS print dialogs; browsers cannot be assumed to provide unrestricted classic Bluetooth or raw TCP printer access.
- Existing printer settings stored one local printer, paper width, copies and automatic receipt preference. Receipt formatting and authoritative shift/Z Report printing already existed.
- No centralized stations, product/category kitchen routing or durable print delivery ledger existed. No restaurant table/open-order lifecycle exists to extend safely.

## Implemented

- Additive centralized receipt, kitchen and bar stations, assigned to a real company/shop/branch/register. Multiple stations per register; archive by disabling rather than deleting history.
- Shared dark-green POS/Backoffice management screens: compact feature hub, stations, product/category routing and delivery queue. Browser Back, mobile forms, visible status and concise errors.
- Existing POS local pairing/discovery/settings remain available for backwards compatibility. Backoffice can configure and queue work; only the assigned POS register performs hardware delivery.
- Bluetooth/USB reuse the existing native bridge; new Android LAN ESC/POS source supports RFC1918 IPv4 on port 9100 only, with connection timeout. No backend sockets, DNS targets or arbitrary ports.
- Chrome uses its OS print service, which can include OS-installed USB/network printers. Direct Bluetooth/USB/LAN printing requires Android. New LAN capability is checked explicitly; older APKs receive an actionable compatibility error.
- 58mm/80mm KOT layouts and existing receipt formatter. Tickets include original order/receipt number, original transaction time, table, cashier/waiter name, routed quantities/units, variant names, preparation/item notes and duplicate label. Product/category routes deduplicate the same item within each station.
- Receipts use authoritative persisted sale fields, including discounts, tax and currency snapshots; there is no new financial calculation or inventory mechanism.
- Automatic online-sale station dispatch runs after sale commit. Financial transaction success never depends on printer success. Local non-financial intents survive temporary enqueue failures and are bound to company/cashier/register.
- Immutable document/printer snapshots with hashes, unique original-sale/station identity, row-locked enqueue and claim, at most five delivery attempts, idempotent result acknowledgement and explicit uncertain status.
- No automatic retry after uncertain delivery or a claim-response timeout. Authorized recovery requires a reason and acknowledgement of duplicate risk; an active attempt has a 60-second recovery guard. Physical exactly-once output cannot be guaranteed by unacknowledged ESC/POS hardware.
- Permissioned reprinting, one-use Phase 7B manager approval for restricted receipt reprints and print retries, protected audit events. Same-register cashier changes cannot inherit another cashier's jobs or local intents.
- Offline synchronization retains the existing financial queue protocol. Synchronized offline sales are NOT automatically reprinted or sent as delayed kitchen tickets. Device-local print-review intents remain visible; confirmed paper output can be resolved through an audited backend review without altering any sale or offline queue.
- Print text strips ESC/POS control characters; ticket HTML escapes user content. Printer addresses/routing references are validated and tenant/branch/register ownership enforced server-side.

## Backend/API additions

All routes below are additive under `/api/printing`, require existing authentication and use existing permission infrastructure:

- `GET /options/{company_id}`: safe register/branch/shop/product/category names, not activation keys or product costs.
- `GET /stations/{company_id}`, `POST /stations`, `PUT /station/{id}`.
- `GET|POST /station/{id}/jobs`.
- `POST /jobs/{id}/claim`, `/result`, `/retry`.
- `POST /offline-review/{sale_id}`: audit a print-only review.

Original printing is cashier-bound; reprints require the reprint permission or action-specific manager approval. Management requires `printers_manage`. Delivery is register-bound. Restricted employees see only their own jobs; authorized administrators retain scoped management visibility.

## Migration requirements

New migration: `p7d_printers_kitchen_jobs`, parent `p7c_employee_roles_permissions`.

```
p5h_runtime_write_permissions
  -> p7a_product_composites
  -> p7b_variant_pricing_tax
  -> p7c_employee_roles_permissions
  -> p7d_printers_kitchen_jobs
```

Adds `printer_stations`, `printer_routes`, `print_jobs`; no historical table/data rewrite. Runtime role gets no DDL or ownership changes. Print snapshot/requester columns cannot be updated by `apex_user`; only job delivery-state columns are updateable, and job DELETE is not granted. Existing protected audit records remain append-only.

Migration review must cover all undeployed Phase 7 dependencies, not just p7d. Production schema was not accessed or migrated in this work.

## Automated verification

- Full backend regression: **289 passed, 110 subtests passed, zero failed/skipped**. Six existing deprecation warnings: Pydantic class config, Starlette/httpx and Python invalid-escape warnings.
- New printer tests cover input/network restrictions, canonical hashes, receipts, kitchen routing, role/company/branch/register isolation, subsequent-cashier isolation, authenticated HTTP routes, manager approvals, uncertain delivery, retry limits, immutable snapshots, offline review and real independent-connection PostgreSQL enqueue/claim concurrency.
- Final targeted verification after the explicit retry-permission revocation guard: **21 printer tests and six subtests passed**, zero failures/skips; three existing Pydantic warnings.
- POS/Backoffice: **23 regression/lint/build commands passed**. Existing lint advisories remain; new printer sources introduce none. Production builds succeed with existing public entitlement verification keys; no signing keys generated.
- Android `:app:lintRelease` and `:app:testReleaseUnitTest`: **BUILD SUCCESSFUL**, zero lint errors, 18 existing warnings. Gradle unit-test smoke: one existing test passed. Separate JVM checks exercise four allowed and ten forbidden LAN targets, plus native transport/permission source assertions. No assemble/package/install task ran and no APK was produced.
- Browser: **32 responsive screen checks** across both apps at 1440, 820, 390 and 320px; feature navigation/Back and restricted-menu checks passed. Delivery fault tests confirm concurrent local send exclusion, no uncertain auto-retry, no print after claim timeout, native-failure quarantine, cashier-bound offline review, unchanged financial-queue sentinel, HTML/control escaping and both paper widths.
- Actual React screenshots: **20 PNGs**, including POS/Backoffice screens and 58/80mm KOT render previews. Synthetic data only; production URLs blocked during browser capture.
- Migration upgrade/downgrade/forward recovery passed on `apexretail_phase7c_rehearsal`, cloned from synthetic Phase 7B fixtures, NOT production. All **43 pre-existing tables** retained identical row counts and SHA-256 content hashes across each stage. Nonempty baseline: sales **1105.00**, stock **113.000**, historical shift links **0**; no fabricated associations. See migration evidence for individual counts/hashes. This is not a substitute for protected current-production-clone rehearsal.

## Remaining limitations and manual gates

1. Physical Bluetooth/USB/network printers, drawer/cutter behavior, paper/encoding, connection interruption and Android WebView hardware behavior require real-device acceptance. System dialogs/bridge submission do not prove that paper printed. Hardware status is shown as unknown rather than fabricated.
2. LAN support is native source only until a separately authorized Android APK update. The existing APK, package, signer, permissions and stored application data were not changed.
3. KOTs are based on completed sales. Pre-payment table orders, separate waiter assignment, open tabs, course firing, order amendment/cancellation tickets and kitchen display systems are not implemented because no existing authoritative order model supports them. Table/notes are print metadata, not financial/order records.
4. Offline printing retains the legacy local path; centralized offline jobs are held for explicit review after synchronization to avoid duplicate receipts or stale kitchen orders. A cashier/device-local print outbox is not automatically transferred between registers. Storage-corruption/quota errors preserve raw state and require operator recovery.
5. Existing direct legacy receipt/Z Report printing remains compatible; it does not gain hardware acknowledgement or centralized delivery history automatically. Centralized station workflows provide the new delivery ledger.
6. Product/category routing selectors currently return up to 1,000 choices each. Larger catalogs need a paginated picker before broad rollout.
7. An explicitly authorized retry of uncertain physical output can duplicate paper; operators must inspect the printer first. Printing cannot duplicate backend financial or stock operations because printer service/worker never submits them.
8. Before deployment: approve UI, rehearse all pending migrations on a protected fresh production clone, verify runtime privileges and backups, accept real printers/platforms, and approve a coordinated backend/frontend release. Archive/review pending printer jobs before any p7d downgrade; dropping its new tables loses printing history, not financial records. Prefer forward recovery after production use.

## Safety

Production services, database, frontend assets, currency settings, enforcement flags, installed APKs, existing queues and signing credentials were not modified. Mandatory shift enforcement was not enabled. Only isolated development worktrees and explicitly named disposable databases were used. Deployment is **NOT authorized by this report**.
