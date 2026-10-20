# Phase 7E continuation — tips, recovery and pharmacy returns

20 October 2026. Continued directly from
`ff05b36b40196e369ad3f4324cf7eea2dee9af8f` on the existing isolated
`phase7e/integration-functional-completion` branch. No rebuild of the system.

Status: **development review candidate; Phase 7E remains PARTIAL / NO-GO for
production** until the remaining acceptance gates below are resolved. The owner’s
tip-policy decision is implemented; it is no longer an unresolved design choice.

## Completed tip functionality

Backoffice → Settings → **Tips & Service Charges** provides:

- Staff tips: entitlement belongs to the original restaurant waiter, or to the
  cashier recorded on a non-restaurant sale. No arbitrary cashier reassignment.
- Shared tips: configurable eligible employees and positive integer weights.
  Only active configured staff in the processing branch receive shares. Equal
  weights implement equal sharing. Allocation conserves currency minor units,
  with deterministic largest-remainder rounding and immutable employee shares.
- Business tips: separately identified business income, with owner confirmation
  that retention is permitted. No employee allocation is fabricated.
- A separate reviewed non-stock/service product for service charges. Its existing
  sales/tax calculation remains authoritative; tips do not use that product.

The new `tip_settings`, `tip_entries` and `tip_entitlements` tables are separate
from products, sales revenue, stock and expenses. No historical sale or old tip
product is reclassified. A tip is recorded as a separate, **already confirmed**
cash/card/mobile-money transfer, with original sale, processing shift, policy,
currency precision, reason, optional provider reference and audit actor.

These APIs record transfers; they do **not** charge cards, contact a payment
gateway, initiate mobile transfers, execute payroll or make bank payments. The
operator confirms that the transfer actually happened. The product receipt and
its tender/change calculation remain unchanged. A separate tip can, for example,
record cash change the customer explicitly leaves after checkout.

POS provides separate tip recording after a successful sale and on a settled
restaurant bill. Authorized shift staff can record reversals/payouts; Backoffice
provides reporting and authorized non-cash reversal/payout recording. Cash entries
require the authenticated cashier’s own open register/branch/shop/shift; Backoffice
cannot remotely pretend to be the drawer cashier.

Cash collections/refunds/payouts post once to the **existing shift cash-movement
ledger**. Card/mobile entries never add physical cash. Cash-out availability and
configured exchange rates are checked against backend records. No exchange rate
is inserted or modified. Cash tip totals are already represented in Cash In/Out;
they must not be added again when interpreting expected drawer cash.

Partial/full tip reversals reference the original tip, method and currency, and
cannot exceed its remaining unrefunded amount. Original employee shares, not the
latest policy, determine reversals. A reversal after payout may produce a negative
employee balance, clearly flagged for manager review; no salary deduction or
fictitious repayment is generated. Disabling new tips does not erase outstanding
entitlements or prevent authorized reversals/payouts.

Employee payouts cannot exceed the outstanding entitlement in that branch and
currency. Payouts and reversals are append-only; allocations cannot be changed or
deleted, including by accidental owner-level ORM updates. Company-level locking,
unique request identities and unique per-entry employee allocations prevent retry
or concurrent-request duplication. Client recovery retains the same original
request after a timeout; it never instructs another money transfer. Definitively
validation-rejected requests can be archived and corrected; unknown outcomes and
identity conflicts cannot be silently discarded or assigned new identities.

Permissions added: `tips_collect`, `tips_manage`, `tips_payout`,
`tips_reports_view`. Cashier/waiter presets receive collection permission;
accountants receive report permission. Policy configuration additionally requires
business-settings permission and owner/administrator status for employee actors.
Company/branch/register/session ownership is enforced on the backend. Disabled
employees cannot record new tips. Existing PIN/authentication/device checks remain.

Legacy tip-product businesses must attest to reviewing pending transactions on
every terminal before first saving the separate-ledger configuration. Once opted
in, new product-style tip sales are blocked even if new tip collection is later
disabled. Historical product-tip refunds still use the existing authorized refund
API. Queued legacy transactions are not deleted, rewritten or silently converted;
they need the established authorized review process before activation.

## Reporting and printing

Backoffice offers date/branch filters, method/policy/kind totals, net tip receipts,
separate business-tip income, all-time employee outstanding balances, reversal
warnings, transfer references and CSV export. Summaries use backend totals;
currencies are not combined. Reporting dates are explicitly UTC; existing sales
report business-timezone calculations are unchanged. CSV cells are protected
against spreadsheet formula interpretation.

Shift responses include a separate tip section. Closing stores an immutable
`cashier_shifts.tips_snapshot`; a database trigger prevents changing it after
closure. Reversals recorded in later shifts do not rewrite earlier Z Reports.
Pre-existing closed shifts keep NULL tip snapshots rather than fabricated history.

Backend Z Report PDF/58 mm/80 mm HTML includes the saved tip totals. POS native
ESC/POS summary data also includes the backend tip amounts, with separate short
method/policy labels so long amounts and currency codes fit narrow paper. Existing
printer transports and product receipt calculations are unchanged. Physical paper
delivery, cutter behavior and device rendering are not certified by software tests.

## Offline restaurant recovery

Added read-only confirmation probes for the original unpaid draft/edit payload.
They require the original employee and registered device and compare the normalized
original payload hash. An unknown request returns 404 and creates nothing. A known
receipt restores the original acknowledgement; mismatched payloads or identities
are rejected. The client offers **Check server confirmation**, retains unknown or
conflicting commands and refuses malformed “successful” responses without an
authoritative acknowledgement. Original timestamps and financial queues are intact.

This improves timeout/reconnection recovery. It does not add offline restaurant
payments, offline KOT delivery or unrestricted offline table/bill mutations.

## Pharmacy returns and batch verification

New refunds of pharmacy or already batch-tracked stock create immutable return
holds inside the existing refund transaction. There is no historical backfill.
The stock remains physically recorded, but pending quantities cannot be sold,
adjusted away or released by generic batch assignment. Existing non-batch retail
refund behavior remains on its original path.

POS/Backoffice batch management adds **Inspect held customer returns**. Authorized
staff confirm actual inspection, lot code, expiry and disposition:

- Restock: attributes the already-restored refund quantity to an inspected lot.
  It does not increase stock a second time. Expired returns cannot be restocked.
- Dispose: attributes and removes the returned quantity through the existing
  inventory adjustment service, once, with an immutable disposal-movement link.
  It does not issue another financial refund or create a second stock ledger.

One hold can have one inspection. Request-key and payload checks make retries
idempotent. Holds, inspections and disposal links are append-only and audited.
Expired-restock validation has an explicit safe correction path: archive the
rejected request and separately confirm a revised disposition. Network-uncertain
requests retain their original identity. Physical inspection is an operator
attestation, not an invented pharmacy regulatory or prescription workflow.

## Verification results

- Complete backend suite: **351 passed; 126 permission subtests passed; zero
  failures or skips**. Final raw log in the review bundle. Six warnings remain:
  Starlette/httpx deprecation, three Pydantic class-config deprecations and two
  existing Python escape warnings in PDF tests.
- Nineteen additional tests cover tip allocation, all three policies, cash/card/
  mobile behavior, immutable records/snapshots, partial reversals, payouts,
  negative balances, concurrency, tenant/branch/session/disabled-employee guards,
  historical tip-product refunds, recovery probes and held-return inspection,
  disposal, sale blocking and migration refusal. Existing tests remain enabled.
- All **24 POS/Backoffice test, lint and production-build commands pass**. The
  changed currency/printing test and POS build are rerun after the final native
  summary-data change. Existing lint/build advisories are included in the logs;
  no security warning is suppressed. A new hook-dependency warning was corrected.
- Twelve local Chromium form/action/viewport checks produce twelve actual PNGs
  at 1440, 820, 390 and 320 px. They exercise shared-policy saving, report loading,
  CSV download, timeout/retry with one simulated receipt, and return inspection.
  Actual React components use synthetic adapters; HTTPS application requests are
  blocked. No live transaction is created. The prior 86 first-pass screenshots
  remain historical evidence, not recaptured current screenshots.
- Initial full regression found one test repository double without the newly
  required tip-summary method. The repository interface and fixture were updated;
  existing physical-currency assertions remain. The subsequent full suites pass.
- HTML/PDF and 58/80 mm ESC/POS tests cover tip output, including a long amount and
  currency code. They do not constitute physical printer acceptance.

## Migrations and integrity

New additive migrations:

`p7g_batch_stock_operations → p7h_tips_accounting → p7i_pharmacy_return_holds`.

They extend the existing single chain rooted at deployed
`p5h_runtime_write_permissions`. No deployed migration was edited. No historical
financial amount, ownership, exchange rate, shift link or enforcement setting is
backfilled. Runtime privileges are limited to the new required operations; tip/
return financial records have no UPDATE/DELETE grant and immutable triggers.

The verified 16 October production backup (not today’s live database) was restored
into new isolated `apexretail_phase7e_tips_clone_20261020`, with PUBLIC/application
CONNECT revoked. The full Phase 7A–7E chain passed eleven sequential upgrade,
downgrade-to-p5h and forward-recovery stages. All 34 pre-existing tables (809 rows)
retain their original-column hashes/counts, currency-separated sales totals, stock
totals, historical shift links and enforcement counts. New columns/defaults are
not presented as historical data changes. The empty synthetic rehearsal passed
the same full sequence; populated synthetic regression databases test new writes.

Backup SHA-256:
`da9b191138ff052d48860359efc4ac850f5d5b805cdc2918e3b22e40db0c6e36`.

Separate populated `apexretail_phase7e_tips_guard_20261020` refused a full Alembic
downgrade; all 64 tables and five synthetic tip entries were preserved, and
forward no-op recovery passed. Pharmacy’s exact downgrade function was also
tested against real held refunds and refused removal. After real new financial
writes, use reviewed forward recovery, not a destructive downgrade or an old
backup restored over newer transactions.

## Android and safety boundary

No Android files, bundled native assets, package/signing setup or installed app
were changed. Source still uses `cloud.apexpos.pos`, versionCode 6/versionName 1.4.0.
No APK was built, signed, installed or uninstalled. Native printer source/JVM
guards pass as part of existing frontend checks. Existing sale/shift contracts
remain compatible in regression tests; tip fields/routes are additive. This is
software-level compatibility, not a physical certification of the installed APK.
Older APKs do not acquire the new tip/inspection screens until a separately
approved future build. Legacy tip-product queues require review before opt-in.

No production connection, data/schema write, asset publication, service restart,
currency change, queue clearance or mandatory-shift-enforcement activation was
performed. The original main worktree, previous artifacts and APKs are preserved.

## Remaining blockers / acceptance requirements

1. Exhaustive authenticated end-to-end acceptance of every legacy POS/Backoffice
   Save/Edit/Delete/Search/Filter/Print/Export action is still incomplete. Existing
   regression suites and the targeted new action checks are not a claim of that.
2. Physical Android/WebView cold restart/background/network-loss testing remains.
   Unpaid drafts persist, but cold-start-offline profile/UI restoration is not
   certified. Offline restaurant payment/KOT and advanced conflict resolution
   remain unsupported and must not be advertised as complete.
3. Pharmacy variant lots/returns remain blocked for review. Generic stock totals
   still show physical stock, including held returns; saleable-vs-held display
   integration for older clients needs acceptance. Lot transfers/counting,
   supplier-credit documents and automatic disposal expense posting are not added.
4. Receipt/customer tip slips, payment-provider automation, payroll/statutory tax
   handling and business-tip legal eligibility require business/accountant review.
   Existing profit cards are unchanged; retained business tips are a separate
   income report, not silently included in product profit. No automatic percentage
   service charge or payroll deduction is introduced.
5. Cash refunds/payouts require the authorized owning POS session. Tip-specific
   short-lived manager-approval tokens are not added; existing sales approvals are
   unchanged. Approve the operational manager/handover procedure before rollout.
6. Physical Bluetooth/USB/LAN printing, margins/cutters, real scanners and the
   installed Android client remain manual gates. New native LAN capabilities
   still need a future separately approved APK release.
7. Current production-backup freshness, the protected deployment runner/runtime
   privilege review and a coordinated rollout/recovery review remain required.
   This rehearsal used the known verified October 16 backup and isolated owner
   execution, not the current live deployment wrapper.
8. Reports explicitly use UTC date filters; optional business-local tip reporting
   and pagination beyond the 1,000-entry/options review limits remain improvements.

Do not deploy or build an APK. Review the screenshots, accounting behavior,
remaining gates and migration plan before any separate final approval.
