# Phase 8 — subscriptions, licensing and billing

Development continues from verified Phase 7 commit
`244feca2d119e26152bfedde125dc6dcbcfe5ef4` in the existing project/worktree.
Nothing was published to production or the existing acceptance service. No new
environment/database, Android APK, signing key or business-data reset was made.

## Implemented

- Separate platform-owner console in the existing Backoffice build:
  `?console=platform`. Business email/password accounts and cashier tokens do
  not authenticate it. No public platform signup or default administrator exists.
- Separate bcrypt-hashed administrator accounts, 30-minute opaque revocable
  sessions, persistent failed-password lockout, active-account checks, and
  `super_admin`, `billing`, `support` authorization. Platform bearer credentials
  are separate from business authentication/storage and are rejected by tenant
  APIs. Mutation privileges are checked by the server, not the displayed role.
- Dashboard: business/subscription counts, trials, expiration, upcoming renewals,
  and revenue grouped by currency. Revenue sources are explicitly confirmed
  manual invoice receipts and verified paid legacy checkout sessions; no exchange
  rates or cross-currency summation are invented.
- Business search, subscription/activation/expiry information, license
  suspension/reactivation, plan management, billing history and protected audit
  viewing. Existing business records are never deleted or disabled by expiry.
- Monthly, quarterly, six-month and annual **calendar-month** plans. Configurable
  prices/currency/precision, eight optional module flags, branch/device/employee
  limits and 1–72 hour offline grace within existing signing policy. Plan editing
  uses optimistic versions; issued invoices and current license terms are snapshots,
  not live pointers that rewrite historical prices when a plan is edited.
- Subscription invoices, partial/manual receipts, outstanding balances, payment
  history, paid renewal history and paginated billing records. Outstanding totals
  include all records, not just the visible page. Currency precision is enforced
  with backend Decimal arithmetic; three/four-decimal prices are not rounded into
  legacy two-decimal subscription-summary fields.
- Exactly-once invoice issuance and receipt confirmation using original request
  UUIDs, company/invoice locks and unique receipt references. Full payment renews
  once from the later of now or the existing paid expiry. Partial payment does not
  activate or extend a license. Overpayment and changed retries are rejected.
- Immutable invoice bodies, append-only payments/notices/platform audits, and
  existing subscription history. Billing receipts are separate from POS sales,
  inventory, cashier drawers, receivables and tip ledgers.
- New plans are **opt-in**. Existing tenants retain their original trial/hosted
  billing behavior until an authorized commercial invoice is fully paid. Plans
  below existing active usage are rejected, not implemented by disabling staff,
  branches or devices. Active claimed terminals count toward device limits.
- Current server limits govern branch creation, employee creation/reactivation
  and existing device activation paths. Plan module restrictions are combined
  with, and never replace, employee/company/branch permissions. Sales, imports,
  product tools, variant inventory actions, restaurant/pharmacy/hospitality/
  wholesale writes, kitchen printing and advanced financial-summary reports have
  server checks. Wholesale quotation actions do not incorrectly require a
  restaurant license. Core historical reads and queue reconciliation remain
  available according to existing employee permissions.
- Frontend gates for optional product tools and business-profile features;
  owner billing/history/notices under existing Backoffice subscription settings.
  Commercial accounts do not see the incompatible legacy renewal form.
- Signed entitlement snapshots now optionally include plan features/limits and
  cap grace at the stored commercial boundary. Final fractional grace seconds
  yield non-writable authorization rather than an invalid snapshot or extended
  license. New offline carts check **verified signed claims**, not unsigned local
  flags. Unknown legacy cached product types fail closed when a commercial
  composite restriction cannot be verified. Existing queued transactions are
  neither rewritten nor discarded.
- Deduplicated in-app trial-expiry, renewal, expiration and full-payment notices.
  An explicit scheduler entry point is provided; no timer or external messaging
  service was installed or activated.

## Legacy hosted billing safety

Existing hosted checkout, signature verification and payment handling are reused.
Managed commercial accounts cannot invoke legacy monthly/yearly checkout to
bypass their commercial contract. Outstanding hosted checkouts must be reconciled
before commercial adoption. A late verified legacy payment is retained in
subscription history and platform audit as `legacy_payment_needs_review`, without
overwriting commercial terms or silently extending the license. Already-paid
hosted references cannot be posted again as new manual receipts. Exceptional
allocation/reconciliation requires operator review; it is not automated.

## Database changes and rehearsal

New additive revision: `p8a_commercial_billing`, descending from
`p7j_variant_batches` with one migration head. Existing deployed migrations were
not edited.

New tables: `platform_admins`, `platform_sessions`, `platform_audit`,
`billing_plans`, `billing_invoices`, `billing_payments`, `billing_notices`.
One nullable opt-in column: `company_subscriptions.commercial_terms`.
No plan/license/payment backfill, default admin, price seeding or currency-setting
change occurs. Existing companies remain unmanaged by the new plan restrictions.

Upgrade → downgrade → forward recovery passed on the **existing disposable
restored backup clone**. All original-column hashes/counts remained unchanged:
34 historical tables, 809 rows. Application CONNECT to that protected clone
remains disabled. Existing allowlisted rollback-only test databases were upgraded;
none were created or reset. Populated commercial data prevents destructive
downgrade; use reviewed forward recovery after any commercial activity.

This archived-clone evidence is not a claim that a current production backup was
taken or that Phase 7/8 migrations are deployed. Fresh production preflight,
backup/restore verification and the protected schema-owner runner review remain
required before any separately authorized release.

## Verification

Final complete backend suite: **430 passed, 158 subtests passed**, no failures or
skips, and six existing deprecation warnings. All 24 frontend test/lint/build
commands passed, as did 13 platform browser assertions and 44 catalog assertions.
Focused Phase 8 coverage: 24 tests plus 12 subtests, including actual authenticated
ASGI API requests against rollback-only PostgreSQL fixtures, not mocked billing
database operations. Coverage includes activation, partial payment, renewal,
expiry/grace, suspension/reactivation, current role checks, company isolation,
capacity/feature enforcement, monetary precision, duplicate receipts, immutable
records, late hosted payments, timestamp boundaries, quotation compatibility,
pagination and populated-downgrade refusal.

All 24 existing POS/Backoffice npm test/lint/build commands passed. Signed
entitlement/rotation, checkout, offline queue, permissions, shifts, currencies,
credit, expenses and Android printer source checks were retained.

Browser acceptance: 13 platform console assertions and 44 catalog component
regressions passed. These browser fixtures use **synthetic adapters**; they are
not represented as deployed HTTPS/provider acceptance. Actual server-side
authentication and database writes are covered separately by the ASGI/PostgreSQL
tests. Screenshots use synthetic values only, at 320/390/820/1440px and desktop
plan/billing views. No external browser requests or uncaught exceptions occurred.

Known non-failing warnings: existing backend deprecations, existing frontend
lint warnings and build chunk-size advisories. No security lint suppression was
introduced.

## Review/rollout gates and limitations

1. Owner review of the console, commercial rates, currencies, limits, enabled
   modules and grace policy. No commercial charges or business plan assignments
   were made outside isolated tests.
2. Explicit platform account provisioning after an authorized migration using
   `python -m scripts.bootstrap_platform_admin EMAIL` with a private interactive
   password. No credentials were invented or stored in reports. Additional
   platform admin account-management UI/MFA is not implemented in this phase;
   account provisioning and role assignment remain protected operator tasks.
3. Configure the approved reminder schedule after deployment. Notifications are
   currently **in-app**; email/SMS transport and external delivery are not
   configured or claimed tested. `python -m scripts.generate_billing_reminders`
   is an explicit operator/scheduler command, never an automatic startup action.
4. New commercial invoices use verified **manual** payment confirmation. Existing
   legacy Paynow remains supported; automated gateway checkout for configurable
   commercial invoices and exceptional late-payment allocation are not provided
   as automatic actions. Provider credentials and live payment acceptance were
   not used or tested.
5. Physical Android acceptance and restricted offline-plan compatibility remain
   pending. Older installed clients do not gain the new UI merely from these
   source changes. No new APK was built. Offline revocation is necessarily bounded
   by the already signed token lifetime, not instantaneous; the server rejects
   unauthorized synchronization without silently deleting or reassigning queues.
6. A production release needs a fresh verified backup, coordinated pending
   migrations, protected runner/permissions review, signed-keyring validation,
   tenant/operator acceptance and explicit authorization. Do not run an older
   backend that ignores commercial policy after commercial licenses are issued.

**Development implementation is verified for the tested scope; production
commercial launch is not approved/claimed READY.** Phase 9 ZIMRA fiscalisation
was not started. These subscription invoices are not claimed to be fiscal
receipts or a substitute for the separate fiscalisation milestone.

Durable report, logs, migration hashes, synthetic screenshots and checksum
manifest: `/root/apexretail-pos/artifacts/phase8-commercial-20261020/`.
