# Phase 10 final production safety preparation

21 October 2026 UTC. **Prepared, not deployed. Production execution: NO-GO pending approvals below.**

Continues preparation commit `f52f2826283a183d3d020d0bca12bb80134f3025`.
Runtime candidate remains `932557e3abca1a2fa046b2d04d0d6f8c6d4bcc35`.
These additions are operational proposals/tests, not a new application or a runtime release.
See `PHASE10-RELEASE-PREPARATION.md` for the complete migration graph and earlier evidence.

## Confirmed production state

- Database **apexretail_pos**, revision **p5h_runtime_write_permissions**, owner postgres.
- API `ok:true`; POS and Backoffice HTTPS 200. API, health timer and backup timer active.
- Mandatory shift enforcement OFF; all **five open shifts** preserved.
- Read-only comparison to the verified 07:22 UTC backup baseline: all **34 historical tables / 886 rows**, original-column content hashes and exact currency/company-grouped numeric control totals unchanged. No historical links fabricated.
- Existing apex_user public-schema CREATE privilege is unchanged, not a grant introduced by this work. No ownership/privilege changes were made.
- Live Nginx configuration hashes still match prior preparation evidence. No service restart, job change, live config installation, schema migration, business write, APK build or offline-queue operation occurred.

## Scheduled backup correction — uninstalled

The active daily 02:00 job `/root/apexpos-tools/backup.sh` targets **apexpos**, not apexretail_pos. It copies stale backend/POS paths, writes unencrypted SQL, lacks fail-fast handling, prints completion even after failure, and uses recursively scoped `find ... rm -rf` retention. A successful unit result is not proof of a valid current POS backup.

No job was executed or edited. Existing `/root/backups` history remains untouched. The old timer still runs with these known defects until a separately approved correction; this is an operational risk requiring prompt owner action.

Prepared files:

- `ops/phase10/backup_proposal.py`: fixed local-socket **apexretail_pos** custom-format pg_dump under postgres with read-only transaction settings; streams directly to GPG encryption, no plaintext temporary dump. Both child exit codes must succeed before atomic publication. Failures retain private partial evidence and exit nonzero.
- `ops/phase10/backup.json.example`: intentionally invalid recipient placeholder; requires the independently verified full public-key fingerprint and a private root-owned GPG home. No private key is needed by the backup job. Trust must be explicitly provisioned; no always-trust override.
- `ops/systemd/apexpos-backup-correction.conf.example`: proposed replacement ExecStart only. No timer schedule change. Proposed installed code `/opt/apexretail-backup/backup_proposal.py`; not installed.
- Proposed output `/root/apexretail-pos/backups/scheduled-production`, root0700; output files0600 via umask. Ciphertext checksum/manifest record `restore_verified:false` until separately restored.

**Retention is preserve-all by default. No deletion/pruning is implemented.** Owner must approve retention, capacity alarms and encrypted off-host storage separately. This is a database-backup correction, not a complete disaster-recovery package: source/config, media, entitlement keys, roles and MFA recovery also require protected coverage.

Synthetic encryption/decryption round trip passed using a temporary test-only key. It did not read production or invoke the proposed job. Real recipient identity/trust, private-key escrow and an actual encrypted database restore remain pending. Do not call custom-format compression encryption.

### Existing verified backup

Private directory:
`/root/apexretail-pos/backups/phase10-release-preparation/20261021T072213Z-932557e/`

`apexretail_pos.dump`: 241,577 bytes, root0600 in root0700 directory.
SHA-256 `a69ea01ff53bf196e36dc3491d76fdecc0a47e70c60adde3a5230d101a9403d7` rechecked; archive catalog readable. This **unencrypted** backup was fully restored twice in the preceding verified preparation; those clones were reused, not recreated. It is outside web roots, but approved encryption/off-host protection is still needed. Repeat a fresh snapshot/baseline before authorized cutover; never overwrite newer financial writes with this snapshot.

## Protected schema-owner runner — prepared and rehearsed, not installed

Builder `backend/scripts/prepare_phase10_protected_bundle.py` extracts backend directly from candidate Git commit, pins the snapshot helper to f52f282, hashes the payload and builds a new root-owned temporary bundle. It does not change the old installed Phase 4 runner or install anything in /opt.

Tested bundle: `/tmp/apexretail-phase10-owner-bundle-y30if_fv`.

- Payload manifest SHA-256: `ea3627e276d09bfc80f08f84090c367c9bb94b1d66ad058723dea44f603e5d9a`.
- Runner SHA-256: `ba72ec501354e0b0c71648151d9d4a1de606de5e545dd04e4dc2597c3132ff06`.
- Payload root:postgres, directories0550/files0440; root-only wrapper0500. PostgreSQL worker can read/traverse the staged source but cannot modify it. Root is the trusted controller; this is not a claim that root is incapable of changes.
- Clean environment, fixed local socket, postgres owner identity, fixed revision/commit, per-file hash and symlink checks, exclusive locks, original-record hash/control-total/owner checks, enforcement OFF and unchanged pre-existing schema privilege.
- Disposable mode permits only names matching `apexretail_phase10_[a-z0-9_]+`, refuses apex_user CONNECT, cannot adopt production as disposable or downgrade production. Baseline is private root-owned evidence.
- Production upgrade requires an exact database/revision/commit confirmation, a private clearance record expiring within 15 minutes, explicit sales/queue clearance and approved open-shift count, loaded/inactive API and watchdog units, application database CONNECT blocked and no other database client sessions. Runner does not create the freeze, stop services or close shifts.
- Permission-tamper test rejected a group-writable payload before connection; original0440 restored. Unapproved production upgrade/downgrade and unexpected database targets rejected. postgres cannot write the protected directories/files.

### Rehearsal results

Exact generated runner on existing application-inaccessible clone `apexretail_phase10_recovery_20261021t072213`:

1. Read-only verify at p10a against original backup baseline: PASS.
2. Downgrade p10a → p5h: PASS.
3. Forward recovery p5h → p10a: PASS.

All original hashes, financial/inventory controls, owners, five shifts, currency data and schema CREATE baseline preserved. Earlier preparation separately tested all 14 pending revisions and full upgrade/downgrade/forward (17 preservation comparisons). No need to repeat those expensive restores.

Before implementation approval: review/install this exact bundle at a protected /opt path, verify ancestor traversal/ACLs and hashes, and repeat the exact installed-context disposable rehearsal. A private archive under backups is retention evidence, not an executable install under /root.

### Maintenance and recovery boundary

Future authorized cutover must capture the exact production database ACL, stop API and both watchdog units, then establish a reviewed **database-specific** connection freeze (including inherited/public CONNECT), drain existing sessions, and take a fresh backup/baseline. Restore the exact prior ACL afterwards; do not blindly grant PUBLIC or set apex_user NOLOGIN globally. No such change was made now. Existing five open shifts need explicit preserve/count approval and terminal queue clearance, not automatic closure.

Clone downgrade is valid only before new Phase 7–10 data exists. Migration guards protect new records. After new billing/fiscal/operational records or financial writes, use reviewed forward-only recovery; do not run an incompatible old backend or blindly restore an older backup. The new wrapper deliberately has no production downgrade mode.

## MFA and initial platform administrator

`ops/phase10/mfa_provision.py` proposes exclusive/no-follow root0600 creation of `/etc/apexretail/platform-mfa.env` in a private root0700 directory. It generates an independent Fernet key directly into the file, never prints it, refuses overwrite and offers boolean-only validation. Temporary fixture provisioning passed; **no production key was generated**.

Existing proposed service drop-in `ops/systemd/apexpos-platform-mfa.conf.example` preserves existing environment and keyring. Require approved encrypted secret escrow and recovery verification before enabling it. Do not rotate an existing key silently.

Reuse `backend/scripts/bootstrap_platform_admin.py` after schema/backend approval: owner selects administrator email/name; password entered with getpass (12–72 UTF-8 bytes), not CLI arguments or chat. Existing duplicate refusal, password hashing, immutable audit and MFA-enrollment requirements were tested on rollback-only fixtures. No production administrator or default credentials created. Complete real authenticator enrollment, session/recovery acceptance and owner identity verification during approved onboarding.

## admin.apexpos.cloud TLS/Nginx

Existing DNS A points to the VPS (187.77.179.100). The existing certificate does **not** cover admin.apexpos.cloud; valid HTTPS on that hostname remains a deployment blocker.

Reuse the previously prepared ACME bootstrap and final templates in `ops/nginx/`. Proposed dedicated certificate and new vhost preserve existing POS/Backoffice/API routes; only `/api/platform/` proxies to existing backend. Other tenant APIs return404. No production CORS relaxation, credential exposure, caching or token URL logging. The console remains the existing Backoffice application entry, not another application.

Four private loopback Nginx tests passed: syntax, redirect/ACME, SPA/security headers, authorized-header forwarding, unauthorized response handling and blocked tenant/sensitive paths. Synthetic certificate only. No live certificate issuance, Nginx edit/test reload or DNS change occurred this turn. Real certificate issuance/renewal and final live vhost need approval.

## Automated results

| Check | Result |
|---|---|
| Full backend regression | **503 passed + 214 subtests; 0 failed/skipped; 6 warnings** |
| Targeted safety/admin/Phase8/10 tests (overlap full suite) | **51 passed + 27 subtests; 3 warnings** |
| POS/Backoffice regression, lint and local builds | **25/25 commands passed** |
| Private Nginx template tests | **4 passed** |
| Exact temporary runner downgrade/forward/preservation | **PASS** |
| Payload permissions, unapproved production refusal, write-tamper refusal | **PASS** |
| Synthetic backup encryption/decryption | **PASS; not a production encrypted restore** |
| Read-only live health/data-baseline comparison | **PASS** |

Backend warnings are existing Starlette/httpx and Pydantic deprecations plus two invalid-escape test warnings. Frontend lint has existing 2 POS/8 Backoffice warnings; both builds have chunk-size advisories. No runtime source fixes were needed. Local test builds are not approved production artifacts. Earlier 396 application-role clone checks and117 API contract comparisons remain valid for unchanged runtime candidate; not rerun or counted as new tests.

## Exact approvals and outstanding gates

1. **Backup operations:** approve replacement of existing backup ExecStart (not timer schedule), protected code/config locations, verified encryption recipient/trust, encrypted key escrow/off-host destination, restore procedure and capacity/retention policy. Preserve all existing history; separately authorize any future pruning. Real encrypted database restore must pass before routine-backup acceptance.
2. **Migration mechanism:** approve protected /opt bundle installation, least-privilege traversal/ACL setup and installed-context disposable rehearsal. Production permission/config changes are not approved by this document.
3. **Secrets and onboarding:** approve MFA key creation/escrow, systemd EnvironmentFile drop-in and intended initial administrator identity; then supervised enrollment/recovery acceptance. No credentials in chat.
4. **Domain/TLS:** approve the narrowly scoped ACME bootstrap, certificate issuance/renewal and final admin vhost; `nginx -t` before separately approved graceful reload. Existing host routes must stay untouched.
5. **Coordinated release:** separate approval for exact backend/frontend artifacts, all14 pending migrations, service/watchdog maintenance, temporary database-specific freeze and exact ACL restoration, preservation of five open shifts and operator terminal queue clearance. Frontend/secret/config snapshots and fresh restore-verified DB backup required. No production implementation is authorized by preparation alone.

Production remains healthy and unchanged. **Preparation software checks passed; deployment and real key/TLS/onboarding acceptance remain PENDING. Do not deploy yet.** Physical Android/printer acceptance remains separate, not claimed here.
