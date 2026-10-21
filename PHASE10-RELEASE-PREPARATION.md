# Phase 10 — production release preparation (NOT deployment)

Runtime candidate: **`932557e3abca1a2fa046b2d04d0d6f8c6d4bcc35`**.
Preparation continues on `phase10/platform-management`; added scripts/docs do
not change that candidate's application logic, API contracts or migrations.
Date: 21 October 2026 UTC.

## Decision

**NO-GO for production execution yet.** Backup restore, complete pending-chain
rehearsal, software security and compatibility checks passed. Production still
needs approval for the release-specific owner runner, credential provisioning,
certificate/vhost, full backend/frontend release and scheduled-backup correction.
No production service, schema, business record, Nginx file, DNS record, secret,
APK or offline queue was changed. Only the explicitly authorized online backup
read production data; all migrations/restores ran on new isolated databases.

## Backup findings — important

The scheduled `apexpos-backup.timer` is active; its last service result reports
success. However `/root/apexpos-tools/backup.sh` invokes `pg_dump` for **`apexpos`**,
not the live **`apexretail_pos`** database. Its latest dated directory is
`/root/backups/2026-10-21_02-00/`, with `apexpos.sql`. Its source paths also refer
to older `/root/apexpos` and `/root/apexpos-web` locations. **A successful timer is
not evidence of current ApexRetail database/release coverage.** The job was not
executed, edited, disabled or restarted by this preparation.

The latest previously verified ApexRetail release archive remains:

`backups/phase5-navigation-production/20261016T112917Z/apexretail_pos.dump`

Its approved SHA-256 was revalidated:
`da9b191138ff052d48860359efc4ac850f5d5b805cdc2918e3b22e40db0c6e36`.
Its archive catalog is readable; previous full-restore evidence is retained.
The older Oct 16 Phase 5 UI archive catalog was also readable (381 catalog lines);
this is not presented as a fresh restore of that older archive.

### New production backup and two verified restores

Persistent private backup directory (root-owned **0700**):

`/root/apexretail-pos/backups/phase10-release-preparation/20261021T072213Z-932557e/`

File: `apexretail_pos.dump` (**0600**, root-owned), **241,577 bytes**.
SHA-256:
`a69ea01ff53bf196e36dc3491d76fdecc0a47e70c60adde3a5230d101a9403d7`

Production connection was explicitly `REPEATABLE READ READ ONLY`, verified
read-only, with an exported snapshot shared by baseline queries and `pg_dump`.
Custom-format dump preserved owners/ACLs, catalog verification passed, and full
`pg_restore --exit-on-error --single-transaction` succeeded twice. No production
pause, write freeze, ownership change or application-role elevation was used.
This follows PostgreSQL's documented [consistent backup](https://www.postgresql.org/docs/current/app-pgdump.html)
and [snapshot-sharing](https://www.postgresql.org/docs/current/functions-admin.html#FUNCTIONS-SNAPSHOT-SYNCHRONIZATION)
mechanisms. Plain hashes/control totals, not business rows, appear in reports;
the dump and detailed baselines are private, outside all web roots.

New isolated databases, both application-inaccessible:

- `apexretail_phase10_fresh_20261021t072213`
- `apexretail_phase10_recovery_20261021t072213`

Both retain owner `postgres`; CONNECT/TEMP were revoked from PUBLIC/apex_user,
and no non-superuser login can CONNECT. Existing databases were never reset or
overwritten. Clones remain for reviewed follow-up; no cleanup/destruction was run.
An initial preparation-harness attempt stopped at database creation because of
transaction handling; it was corrected before retry. Its valid backup remains
private. Final restore/migration checks all passed; no production failure occurred.

This is a logical single-database backup, not PITR or complete off-host disaster
recovery. Roles/server config, external media, entitlement keys and the future MFA
key need separately protected recovery material. Approved encrypted off-host
retention and a corrected routine backup/restore verification are release gates.
Normal production writes can occur after the snapshot; repeat backup/baselines
under the approved maintenance procedure immediately before actual cutover.

## Database compatibility and preservation

Live revision confirmed: **`p5h_runtime_write_permissions`**. Mandatory shift
enforcement: **OFF**. Five open cashier shifts were present and preserved; none
were closed or reassigned by preparation.

The single migration head is `p10a_platform_management`, with exactly 14 pending
migrations, in order:

```
p5h_runtime_write_permissions (production)
 → p7a_product_composites → p7b_variant_pricing_tax
 → p7c_employee_roles_permissions → p7d_printers_kitchen_jobs
 → p7e_business_orders_batches → p7f_offline_order_receipts
 → p7g_batch_stock_operations → p7h_tips_accounting
 → p7i_pharmacy_return_holds → p7j_variant_batches
 → p8a_commercial_billing → p9a_fiscal_preparation
 → p9b_fiscal_protocol → p10a_platform_management
```

Each pending revision passed separately on the fresh clone. The separate recovery
clone passed full upgrade, downgrade to `p5h`, and forward recovery to `p10a`.
All **17** stage comparisons preserved **34 historical tables / 886 rows** with
identical original-column content hashes and exact numeric control totals grouped
by company and persisted currency identifiers (no exchange-rate conversion).
Existing table owners, five open shifts, enforcement flag and pre-existing schema
CREATE privilege were unchanged. Added columns/defaults are intentional schema
extensions, not historical transaction edits or invented shift associations.

The installed protected runner is still pinned to hotfix
`4fe499fa363706e5757c763a8b19d242c30c928a` and `p5g → p5h`. **Do not repurpose or
execute it for Phase 10.** The new preparation script deliberately has no live
migration/restore execution mode. A release-specific protected owner runner must
be staged, reviewed, hash-pinned and rehearsed in its installed context before
production authorization. Preserve root ownership, narrowly scoped read/traverse
access, existing ownership and credentials; do not give `apex_user` new DDL rights.

### Recovery boundaries

The successful schema downgrade test used a restored baseline **without new
Phase 7–10 operational data**. It is not approval for a production downgrade.
Existing security/fiscal/billing migration guards reject downgrades that would
destroy new records; regression tests exercise these guards. After enrollment,
new operational records or financial writes, prefer reviewed forward recovery.
Never restart an incompatible old backend or restore an older database over
newer transactions. A frontend rollback may restore its verified asset snapshot
without clearing storage, but backend/schema rollback is a separate decision.

## Runtime and endpoint compatibility

The fresh migrated clone was checked under `SET LOCAL ROLE apex_user` inside a
read-only transaction. **396 checks passed** across 21 existing owner accounts:
model/table reads (zero-row schema probes), representative product/variant,
inventory, sales history, employees, shift reports, currencies, receivables,
settlements, expenses, licensing and financial-report endpoints; owner tokens
were denied platform access, and cross-business requests were denied. No private
response bodies, passwords or tokens were logged; no real transaction was made.

Offline comparison with the current public production OpenAPI found all **117**
deployed operations present, with **no newly required top-level JSON/query/path
inputs**. This is a structural check, not a claim that every possible client
behavior or physical Android/printer interaction was tested.

All third-party imports referenced by the candidate are available in the existing
production Python environment. An isolated candidate import/OpenAPI generation
using that interpreter succeeded (26 platform paths), without connecting a
database, starting a server or altering the environment. This does not replace
the protected migration runner's installed-context/privilege rehearsal.

Live POS and Backoffice returned HTTPS 200; API health returned `ok:true`.
`apexpos.service` and `apexpos-health.timer` remain active. The latest configured
backend override references release `340faad2802246d8f29ab3c0f3de9352612f7136`;
do not infer the live release from the older working-tree HEAD. Production still
has no Platform Admin API paths; candidate console access is verified in isolated
tests only, not represented as live.

## MFA provisioning proposal — no secret created or installed

Uninstalled drop-in: `ops/systemd/apexpos-platform-mfa.conf.example`.
It adds only `EnvironmentFile=/etc/apexretail/platform-mfa.env`; existing DB,
authentication, entitlement and other environment settings must remain intact.

After explicit approval, an authorized root operator must:

1. Create private root-owned config directory 0700 (if absent), verify it is not
   a symlink, and create a new env file using exclusive creation/no-follow with
   mode 0600. Never overwrite an existing key or use shell tracing.
2. Generate one independent Fernet key directly into that file as
   `PLATFORM_MFA_KEY=...` using the existing cryptography dependency. Do not print,
   paste into chat/CLI arguments, derive from JWT keys or store in Git/artifacts.
3. Verify owner/mode/validity using a boolean-only local check; place a restricted,
   encrypted recovery copy in an owner-approved secret store. Verify recovery
   without displaying the key. Loss/replacement requires reviewed factor recovery.
4. Install the reviewed drop-in, preserving the current entitlement drop-in and
   all other configuration. Reload systemd/start only the required API during
   the separately approved cutover; no such operation was performed here.
5. Provision the intended initial platform administrator via the existing local
   bootstrap procedure, verify recipient identity, and complete MFA enrollment.
   No default credentials, backdoor, business-password access or impersonation.

Tests verify missing/invalid keys fail closed, secrets are masked, password-only
sessions are rejected, MFA replay/lockouts work, and billing/support roles cannot
perform root-only management. Environment/secret-store provisioning itself and
real authenticator acceptance remain pending. Session data on the new admin
origin is separate: require platform sign-in; never copy business tokens/storage.

## HTTPS and web hosting proposal

DNS A `admin.apexpos.cloud → 187.77.179.100` is correct. A dedicated certificate is
still absent; live HTTPS returns hostname mismatch (curl 60). Existing shared
certificate covers API/POS/Backoffice only. No certificate/private key, DNS entry,
firewall or renewal config was changed. Issuance needs the approval-gated ACME
bootstrap or an explicitly approved DNS-validation alternative.

Use the existing two vhost templates and procedure in `PHASE10-ADMIN-DOMAIN.md`:
dedicated admin certificate, new vhost only, same Backoffice application/root
`/var/www/apexpos-backoffice`, restricted same-origin `/api/platform/` proxy to
the existing API on 127.0.0.1:8000. POS root stays `/var/www/apexretail-pos`.
No new backend/app/staging deployment or CORS change. Access/token URL logging
and API caching are disabled for the new host. Actual certificate issuance,
combined live `nginx -t`, graceful reload and renewal-hook tests remain pending.
Isolated Nginx syntax, routing and TLS tests passed; temporary test certificate
was never installed. Active Nginx file hashes remain identical to the last review.

## Release checklist and required approvals

- [ ] Approve exact runtime/backend/POS/Backoffice artifacts and checksums; preserve
  existing builds/downloads/configuration for rollback. Do not use a localhost
  verification build or publish only the admin UI against the old backend.
- [ ] Approve correction of the existing scheduled backup script to the actual
  DB/live source/asset paths, protected storage and restore checks; retain existing
  backups. Verify the corrected job and approved off-host recovery coverage.
- [ ] Approve the new protected migration runner for `p5h → p10a`, install and
  rehearse it with the exact staged source/venv and owner privileges. Current
  preparation rehearsal does not certify a not-yet-installed production runner.
- [ ] Approve MFA key/initial-admin provisioning and separately protected recovery.
- [ ] Approve maintenance window; confirm every terminal's pending/failed/
  quarantined queue is reconciled and sales paused. Review the five open shifts
  with the operator: close through normal workflow or approve an explicit
  preservation/handover plan. Do not close them automatically.
- [ ] Acquire exclusive deployment lock, snapshot current service/watchdog state,
  preserve configs and assets, take another fresh verified cutover backup, drain
  requests and establish the reviewed application-write exclusion. Stop only
  the relevant API/watchdog for the approved window, not PostgreSQL/other services.
- [ ] Migrate using the owner runner, compare financial/inventory/currency/shift
  baselines, keep enforcement OFF and live fiscalisation disabled. Abort on drift.
- [ ] Switch matching backend/clients/config atomically using existing controlled
  publishers (hashed assets first, index last). Preserve Android compatibility,
  sessions, offline queues, downloads and keyring. No APK build/install.
- [ ] Approve the dedicated admin ACME certificate/bootstrap/new vhost and renewal
  checks; validate Nginx before graceful reload. Never replace existing routes.
- [ ] Check API/public assets/authentication/MFA/read-only business views, owner/
  employee denials, mobile console, logs, integrity and post-cutover backup.
  Restore original watchdog state, verify it, then release lock.
- [ ] Owner performs real platform login/authenticator, Android/WebView, offline
  recovery and physical printer acceptance. Do not generate fake production sales.

### Downtime and operational risks

Preparation and backup caused no planned outage. Fourteen schema updates require
table locks; an API pause and watchdog coordination are needed during cutover.
Separate clone stage timings total about 13.4 seconds, and a combined upgrade
plus preservation snapshot was about 1.4 seconds on this small dataset. These are
**not downtime guarantees**: backup validation, configuration changes and health
checks dominate the window. Reserve a reviewed 15–30-minute maintenance window
as an initial planning allowance, adjusted by the final installed-runner rehearsal.
Long transactions, device queues, active shifts, key loss, old/new client mixes,
shared certificate changes and an over-broad database restore are principal risks.

## Automated verification summary

- Full backend suite: **491 tests + 199 subtests passed**, six pre-existing warnings,
  no reported failures/skips. Includes platform MFA/RBAC/tenant isolation, billing,
  prior Phase 7–9 regressions and preparation guard tests.
- All **25** frontend regression/lint/build commands passed. Existing warnings:
  POS 2, Backoffice 8 plus bundle-size advisories. No runtime UI edits this task.
- Fresh-clone compatibility: **396 checks passed**; structural compatibility:
  **117 deployed operations retained**, no newly required top-level inputs.
- Migration/restore: two new full restores; **17 upgrade/recovery comparisons**
  passed. Production revision and enforcement remain unchanged.
- Existing vhost templates: four private-loopback Nginx/TLS test cases passed;
  no live Nginx signal or config change. Three preparation guard tests also passed.

Full public endpoint exercise with real production credentials, physical
Android/printers, actual MFA enrollment, certificate renewal and live release
acceptance remain **PENDING**, not claimed as passed. No production test sale,
financial edit, migration, database reset, service restart or APK build occurred.
