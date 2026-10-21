# Phase 10 — installed runner and backup safety preparation

21 October 2026 UTC. Continues `5626040a792cdcb0abaa57b76cef736dbf9e51ff`.
Runtime candidate remains `932557e3abca1a2fa046b2d04d0d6f8c6d4bcc35`.
**No Phase 10 deployment, production migration or domain activation performed.**

## Completed changes

### Exact protected runner installed and rehearsed

Installed the existing verified bundle, not a replacement migration procedure:
`/opt/apexpos-migration-runners/phase10-932557e/`.
The earlier Phase 4 runner remains untouched. No application service points to
this bundle. All production application runtime sources are unchanged from the
previously reviewed candidate.

- Runner SHA-256: `ba72ec501354e0b0c71648151d9d4a1de606de5e545dd04e4dc2597c3132ff06`.
- Manifest SHA-256: `ea3627e276d09bfc80f08f84090c367c9bb94b1d66ad058723dea44f603e5d9a`.
- Parent chain /opt and /opt/apexpos-migration-runners root:root0755; bundle and
  payload directories root:postgres0550, source files0440, root-only wrapper0500.
  Private evidence directory root0700. No application-role DDL grant or table
  ownership change. PostgreSQL can read the required source but cannot modify
  protected files/directories; installed-context read/write checks passed.
- Pinned payload verification, explicit refusal of unapproved production upgrade,
  all production downgrade, production-as-disposable baseline confusion and
  unexpected database names passed before any production connection.

Exact installed runner on existing disposable clone
`apexretail_phase10_recovery_20261021t072213` passed:

1. Verify original baseline/payload/owner/safety flags.
2. Downgrade p10a→p5h.
3. Forward recovery p5h→p10a.

All original hashes, financial and inventory controls, ownership, currency data,
five shifts and pre-existing schema CREATE privilege preserved. This rehearses
all14 pending migrations from the deployed p5h baseline, without touching live
schema. Previous per-revision rehearsal evidence remains valid. Clone downgrade
is not approval to downgrade after new operational records exist; production
downgrade is deliberately unavailable. Use reviewed forward recovery after writes.

Production mode still requires separate authorization, exact confirmation,
short-lived private maintenance clearance, stopped API/watchdog, database-specific
application connection freeze, no other clients and explicit open-shift/queue
clearance. None of those production actions was performed.

### Unsafe retention removed; history preserved

The **only** installed backup-script change this turn was replacing the recursive
`find ... rm -rf` command with a preserve-all comment. The corrected database target
remains apexretail_pos; schedule, service unit, filename and script ownership/mode
remain unchanged. Original script retained privately. Shell syntax passed; exact
diff reviewed. Existing `/root/backups` inventory, sizes and mtimes match before
and after; no old backup was deleted. Exclusive deployment lock was released.

Current script SHA-256:
`0d47d4eaf78dfa0ee17ea4076d3a394c436a020c8b60cf21d79ef6448e7fd9a0`.

The old plaintext SQL format, stale backend/POS copy sources, permissive inherited
output defaults and masked-failure behavior remain existing issues. Do not mistake
this retention correction for complete routine-backup security. The existing
script was not invoked end-to-end; its corrected database dump and full restore
were verified in the preceding task. New retention is preserve-all; capacity must
be monitored (observed65GiB free,34% used), not silently pruned.

### Encrypted storage and restore prepared

Prepared root0700 storage at
`/root/apexretail-pos/backups/scheduled-production`; no public file route.
Existing encryption proposal remains uninstalled because no approved recipient,
private-key recovery custodian or off-host destination has been selected.
Detailed custody/integrity/restore requirements are in
`ops/phase10/RECOVERY-REQUIREMENTS.md`.

New operational test encrypted the existing verified custom dump with an ephemeral
test-only key, checked altered ciphertext rejection, and streamed decryption into
a full transactional isolated restore without creating a plaintext recovery file.
The temporary key/ciphertext were scoped test artifacts, not production backups;
the original verified backup and all history remain intact.

- Source SHA-256: `390e5673e8ec4a0e81706aa9a0bd8874e37d0f4d8e405f15981de39028469965`.
- New application-inaccessible restore clone:
  `apexretail_backup_encrypted_20261021t102947463212`.
- **34 tables /890 rows**, original hashes, exact financial/inventory controls,
  ownership/ACLs and p5h revision matched. No production connection was used by
  this encryption/restore test. Actual owner-key/escrow/off-host acceptance pending.

## Authentication, MFA and HTTPS review

Existing Platform Admin authentication retained: separate opaque hashed sessions;
ordinary business tokens denied; mandatory verified MFA; encrypted TOTP enrollment
secrets; short-lived challenges, lockout/replay protection, scoped roles, revocation,
audits and explicit recovery. Initial administrator remains the existing local
getpass bootstrap, not a public signup/default account. No production password,
MFA key, administrator account or factor was created or logged.

Protected production MFA/config paths are not provisioned. Missing key fails
closed in isolated tests. Owner identity selection, root0600 key creation, approved
encrypted escrow, reviewed EnvironmentFile integration, real authenticator and
recovery acceptance require separate approval after schema/backend readiness.

DNS admin.apexpos.cloud resolves to187.77.179.100. Live HTTPS still fails curl60
because the current certificate does not cover this hostname. No TLS bypass used.
Existing ACME/final Nginx templates passed4 private tests; no live Nginx change,
certificate issuance, renewal configuration or reload was performed. A dedicated
valid certificate and approved vhost remain mandatory before enrollment/login.

## Test and health results

- Relevant isolated backend/security suite: **51 passed +27 subtests**, zero
  failures/skips,3 existing Pydantic deprecation warnings.
- Private Nginx template suite: **4 passed**.
- Installed runner verification, rollback, forward recovery, checksum/least-
  privilege and unsafe-target rejection: **PASS**.
- Real dump encrypted restore with ephemeral test key and corrupt-cipher rejection:
  **PASS**, not presented as production recipient/escrow acceptance.
- Backup shell syntax, sole retention diff and history inventory comparison: PASS.
- API healthy (`ok:true`), POS200, Backoffice200. API/health/backup timers active;
  no restart. Existing Nginx and backup unit hashes unchanged.
- Final read-only production comparison to fresh backup baseline: original hashes,
  numeric controls and owner/ACLs unchanged; database **apexretail_pos**, revision
  **p5h_runtime_write_permissions**, five shifts preserved, enforcement **OFF**.
- No app/frontend source changes; prior503 backend +214 subtests and25 frontend
  regression/lint/build checks remain recorded. They were not rerun or falsely
  counted as new checks. No APK built/installed; hardware tests not claimed.

## Outstanding approvals and decision

1. Approve a verified public backup recipient, private-key escrow/recovery access,
   encrypted off-host storage and monitoring; approve replacement of the remaining
   unsafe legacy job behavior with the prepared fail-closed encrypted job. Verify
   an actual approved-key restore before routine-backup acceptance. Any future
   pruning needs a separately reviewed retention policy; no deletion now.
2. Approve MFA key provisioning/escrow, EnvironmentFile and intended initial
   administrator identity, followed by supervised MFA/recovery acceptance.
3. Approve dedicated certificate issuance/renewal and admin ACME/final Nginx vhost,
   syntax validation and graceful reload. Preserve all existing host routes.
4. Separately approve exact backend/frontend artifacts, coordinated maintenance,
   fresh backup/baselines, terminal queue/open-shift clearance, reviewed database-
   specific freeze/ACL restoration and all14 migrations p5h→p10a. Never blindly
   restore old financial data or restart an incompatible old backend.

**Installed-runner and software safety rehearsals: PASS. Super Admin deployment:
NO-GO pending actual backup key/recovery, MFA/onboarding, TLS and release approval.**

Private persistent evidence:
`/root/apexretail-pos/backups/phase10-installed-safety-20261021/`.
