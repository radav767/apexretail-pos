# ApexRetail Phases7–10 — consolidated controlled deployment plan

**PLAN ONLY — NOT AUTHORIZATION OR AN EXECUTED DEPLOYMENT SCRIPT.**
21 October2026 UTC. Existing application/infrastructure only; no new database,
staging environment, APK or live modification is authorized by this preparation.

## Release identity and actual dependencies

Rehearsed runtime candidate **932557e3abca1a2fa046b2d04d0d6f8c6d4bcc35**.
Subsequent preparation commits add operational tools/tests/docs; application,
frontend source and migrations remain identical. Do not deploy Git HEAD blindly.
Owner must approve the exact candidate and matching production-configured builds.
Operational proposals (including the hardened admin vhost/renewal hook) come from
this separately reviewed preparation commit, not an older runtime checkout. Freeze
and hash those exact files too; do not lose the new restrictions by copying an
old template. The installed backend migration payload remains unchanged.

Alembic graph inspected from source: one head **p10a_platform_management**, exactly
14 pending revisions from live **p5h_runtime_write_permissions**:

```
p5h_runtime_write_permissions (LIVE)
  → p7a_product_composites
  → p7b_variant_pricing_tax
  → p7c_employee_roles_permissions
  → p7d_printers_kitchen_jobs
  → p7e_business_orders_batches
  → p7f_offline_order_receipts
  → p7g_batch_stock_operations
  → p7h_tips_accounting
  → p7i_pharmacy_return_holds
  → p7j_variant_batches
  → p8a_commercial_billing
  → p9a_fiscal_preparation
  → p9b_fiscal_protocol
  → p10a_platform_management
```

| Group | Dependency evidence | Allowed release scope |
|---|---|---|
| Phase7 | Products/variants → employee permissions → printers/business operations → offline/batch/tip/variant-batch models | Verified retail/operations software; relevant hardware acceptance still required |
| Phase8 | p8a directly descends p7j; existing platform identities/billing/session/audit tables created here | Opt-in plans/manual billing; preserve unmanaged businesses and legacy contracts |
| Phase9 | p9a descends p8a; p9b adds protocol state/documents/events | Disabled fiscal preparation/read-only status only, not live compliant fiscalisation |
| Phase10 | p10a descends p9b, alters Phase8 admins/sessions; console fiscal monitoring reads Phase9 models | MFA-protected existing platform console after HTTPS/key onboarding |

`backend/app/main.py` imports/registers printing, business operations, commercial
billing/platform and fiscal routers in the **same backend**. Phase10 dashboard
queries Phase7 operational counts, Phase8 subscriptions and Phase9 fiscal state.
The existing Backoffice entry serves business and platform views; both frontends
integrate the earlier APIs. Therefore: **migrate Phase7→8→9→10 in ancestry order,
then one coordinated full backend cutover, then matching frontends and admin
activation**. Do not start a partially migrated Phase10 backend or run separate
intermediate backend releases just because phase numbers differ.

No Phase9 live service is implied by migrating its tables. Existing code reports
live submission disabled/not certified. Verified HTTP connector, real FDMS test
onboarding/credentials, clarification of documented vectors, device/key lifecycle,
sale/refund/print mappings and formal acceptance are still outstanding. Do not
describe this combined release as ZIMRA-certified or live fiscal-ready.

## Mandatory gates before any live implementation

1. **Backup security first:** approved real recipient/private-key escrow, independent
   off-server destination/retention protections, actual encrypted recovery,
   monitoring and owner-approved scheduler activation. Prior synthetic/same-VPS
   tests alone are insufficient. Keep current history; never age-prune unverified
   files. See `PHASE10-BACKUP-ENCRYPTION-READINESS.md`.
2. **Freeze the release:** archive exact candidate source; build POS/Backoffice with
   reviewed production API and entitlement public-keyring settings; hash manifests,
   lockfiles, toolchain and dependency inventory. Existing test-build dist folders
   may target local APIs/synthetic keys: **not production artifacts**. Preserve
   existing interpreter/environment/config/credentials/keyring; no unreviewed
   dependency upgrade or old deployment script.
3. **Approve operations:** owner selects maintenance window, operator/admin identity,
   secret custodians and hardware acceptance owners. Relevant printer/Android,
   offline queue and representative business workflows require explicit acceptance.
   No new APK or staging system is part of this release.
4. **Prestage secrets/TLS only under separate approval:** private MFA key and verified
   escrow, dedicated admin certificate through reviewed ACME bootstrap or approved
   DNS validation. No final admin console activation before backend/MFA readiness.
5. **Separate module commissioning:** no mass commercial conversion, automated live
   payment capture, notification delivery claim or fiscal activation. Existing
   legacy businesses remain compatible/unmanaged until explicit commercial adoption.

## Controlled execution sequence — future approval required

### A. Recheck and lock

- Acquire `/run/lock/apexpos-production-deploy.lock`; stop if another deployment owns it.
- Verify source, protected runner and all artifact hashes. Installed runner:
  `/opt/apexpos-migration-runners/phase10-932557e/migration_runner.py`.
  SHA256 `ba72ec501354e0b0c71648151d9d4a1de606de5e545dd04e4dc2597c3132ff06`;
  manifest `ea3627e276d09bfc80f08f84090c367c9bb94b1d66ad058723dea44f603e5d9a`.
- Revalidate live DB name/revision p5h, health, disk capacity, active connections,
  current effective backend service/overrides and active Nginx roots. Currently POS
  `/var/www/apexretail-pos`, Backoffice `/var/www/apexpos-backoffice`; verify again,
  do not assume them or create a second deployment directory.
- Operator confirms all terminals paused and queued/pending/failed/quarantined
  financial transactions resolved. Existing five open shifts require explicit
  preserve/count approval or operator closure **before** cutover. Never auto-close,
  transfer another cashier's ownership or delete queued transactions.

### B. Maintenance, freeze and recovery material

- Preserve watchdog configuration/enabled state, temporarily disable and stop its
  timer/service, then stop only the relevant API service. Drain in-flight writes;
  reconcile uncertain submissions. Restore the captured original state at exit.
- Capture exact DB ACLs; establish reviewed **database-specific** application
  connection/write freeze while preserving owner migration access. Never globally
  NOLOGIN the shared role or blindly grant PUBLIC afterwards. Runner expects no
  other client sessions and a short-lived private explicit maintenance clearance.
- Take fresh snapshot-consistent production backup/baselines: original-column
  hashes/counts, company/currency-native financial controls, owners/ACLs, inventory,
  shift links, currency/exchange data, settings, permissions and audit history.
  Verify encryption/off-server readback and restore capability under approved
  recovery procedure. Any isolated restore target must be separately authorized;
  this plan does not permit creating/resetting one or restoring production.
- Snapshot existing frontend assets/downloads, effective backend configuration,
  Python environment, entitlement keyring and secret recovery material privately.
  Preserve all prior backups. Confirm available forward-recovery artifacts.

### C. Full database chain under the tested owner runner

- Use only the installed hash-pinned owner runner and exact staged backend. Its
  explicit production confirmation/clearance is required; do not use the old
  Phase4 p5g→p5h wrapper or manually edit alembic_version.
- Upgrade all14 pending revisions in the order above through p10a. No Phase10-only
  stamp/skip, modification of deployed migrations, table-owner change or new
  application-role DDL grant. Preserve the pre-existing schema CREATE baseline.
- Verify exact final revision, original records/content hashes and native-currency
  controls, owners, shifts, stock, audit data and settings. New nullable/default
  schema extensions are expected; historical financial links/backfills are not.
  Shift enforcement stays OFF, exchange rates unchanged. Stop on any discrepancy.

### D. Matching backend first

- Point the existing service to the exact immutable full backend release. Preserve
  current DB/auth/entitlement environment and keys; add only reviewed MFA config.
- Once ready, restore exact prior connection ACLs and start only the new backend.
  Verify health, auth rejection/success in authorized acceptance, sales/shift,
  products/inventory, expenses/credit, subscription and fiscal-status routes.
  No artificial production sale, refund, invoice or payment.
- Phase9 live transport remains disabled; offline restaurant payments remain
  blocked where unsupported. Do not enable mandatory shift enforcement.

### E. Matching POS and Backoffice

- Publish verified hashed assets first, index.html last using atomic replacement.
  Keep old hashed assets needed by cached clients/rollback; preserve downloads/APKs.
- Do not clear browser/app storage, cashier sessions, printer settings, device
  registration or offline queues. Validate asset hashes and HTTPS200 publicly.
- Check existing installed production Android API compatibility without rebuilding,
  installing, uninstalling or distributing the staging APK as a production update.

### F. Final admin HTTPS and owner onboarding

- Use the existing uninstalled ACME/final admin templates, not a new application.
  For HTTP validation, the temporary new admin vhost serves only the ACME path;
  other requests503. Validate full Nginx configuration before any approved reload.
  Use dedicated certonly/webroot issuance with approved contact/terms and reviewed
  hooks; do not auto-rewrite existing sites or replace their shared certificates.
- Verify dedicated certificate SAN/chain/expiry and certificate/key match without
  exposing the private key. Install final vhost only after matching Backoffice
  assets and backend/MFA are ready. Same-origin `/api/platform/` only; tenant APIs,
  downloads and sensitive files404; credential responses uncacheable/unlogged.
- After `nginx -t`, separately approved graceful reload; verify POS/BO/API remain
  healthy, admin valid HTTPS and unauthenticated platform requests401. No TLS bypass.
- Bootstrap the owner-selected administrator with the existing private local CLI;
  supervise real MFA enrollment/session/recovery acceptance. No default passwords,
  emailed factors, screenshots of secrets, customer-password access or impersonation.
- Install the reviewed admin-only renewal hook only after certificate/final-vhost
  validation; test renewal/alerting under approval using the existing Certbot timer.
  Preserve other lineages and renewals; no API restart from the hook.

### G. Integrity, acceptance and exit

- Repeat historical hashes/financial/inventory/currency/ownership/shift checks;
  only explicitly approved new platform onboarding/audit records may differ.
- Verify tenant isolation, permissions, billing access, idempotent retry references,
  legacy clients, sales/shift/report routes and relevant physical print/Android
  acceptance. Use read-only/non-financial smoke checks wherever possible.
- Obtain verified post-release encrypted/off-server backup under approved recovery
  procedure. Inspect logs without credentials; restore original watchdog behavior
  and confirm timer/health. Release lock/maintenance only after critical gates pass.
- Owner approves resumption of real sales. Do not treat unauthenticated route
  reachability or synthetic tests as complete business/hardware acceptance.

## Phase-specific rollout limits

- Phase7: feature configuration and physical Bluetooth/USB/LAN/58/80mm/KOT routing,
  Android lifecycle/offline recovery remain explicit gates. Do not enable station
  auto-print until its actual routing/duplicate-print acceptance passes.
- Phase8: no invoice/price/license backfill; existing `commercial_terms` remains
  null for unmanaged businesses. Agree plans/limits/currency/grace before opt-in,
  reconcile pending legacy hosted checkouts, use real received-money confirmation.
  Reminders are in-app; external email/SMS and configurable-plan gateway automation
  are not claimed implemented/accepted. Schedulers require separate approval.
- Phase9: migrate disabled preparation/status capability only. No live FDMS calls,
  certification claims, generated regulatory tax rates or automatic fiscal receipts.
- Phase10: same existing platform console; actual key custody, HTTPS, enrollment
  and role/session/recovery acceptance precede public operational access.

## Recovery and downtime

API downtime is required for the agreed write freeze/migration/cutover. TLS and
immutable assets may be prestaged after approval, but final activation waits for
readiness. Exact window duration needs the full artifact-cutover rehearsal and
operator availability; migration timings alone are not a guaranteed outage bound.

If a pre-migration gate fails, do not proceed. If migration/integrity fails, keep
writes paused, preserve evidence and seek reviewed forward recovery. Tested clone
downgrade was on data without new Phase7–10 records; populated migration guards
refuse destructive downgrade. Never restore an old DB over newer transactions or
start an incompatible old backend after new commercial/fiscal/operational writes.

Frontend rollback may restore only its verified asset snapshot (assets first/index
last), preserving downloads/storage/queues and compatible API. Admin-only Nginx
failure can revert only the new vhost/hook after validation while keeping existing
sites intact. These are not authorization for database rollback or key rotation.

**Overall recommendation: NO-GO for execution until owner approvals, real backup
security/recovery, MFA/HTTPS, production artifact manifests and applicable manual
acceptance gates pass.** Current task only prepares/tests/documents this sequence.
