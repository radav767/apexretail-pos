# Phase 10 — backup encryption and recovery readiness

21 October 2026 UTC. Continues verified preparation commit
`25d15f2f1066572511169918cd64133fffcb8e26`.
**PREPARED / NOT ACTIVATED. NO-GO for scheduled encryption until real external
custody/storage/recovery and owner approval are complete.**

## Current production inspection

- Correct live database **apexretail_pos**, revision **p5h_runtime_write_permissions**.
- Existing service still calls `/root/apexpos-tools/backup.sh`; daily02:00 timer
  unchanged. The job still produces plain SQL with legacy filename apexpos.sql.
  It is **not encrypted**; do not represent the uninstalled proposal as active.
- Correct database target and preserve-all comment remain. Unsafe recursive
  deletion removed in the preceding task has not returned. No existing archive
  was moved/deleted; `/root/backups` inventory/sizes/mtimes match prior evidence.
- Backup script SHA: `0d47d4eaf78dfa0ee17ea4076d3a394c436a020c8b60cf21d79ef6448e7fd9a0`.
  Existing service/timer hashes unchanged. Their legacy failure masking, stale
  asset-copy sources and plaintext/default-permission limitations remain; the
  prepared DB coordinator is not claimed to back up all application/config/media.
- Prepared local encrypted storage root-owned0700:
  `/root/apexretail-pos/backups/scheduled-production`. Observed65GiB free/34% used.
  No pruning or monitoring job was installed; preserve-all requires capacity alerts.

## Implemented preparation

| Requirement | Result |
|---|---|
| Production target/config inspection | PASS, existing job remains apexretail_pos |
| Encrypted DB backup proposal | Strengthened public-only key validation, streaming hash, durable metadata publication; uninstalled |
| Key custody | Secret recovery keys refused in scheduler keyring; real custodian/escrow pending |
| Off-server storage | Strict pinned-host SFTP option/config prepared; no real destination selected or provisioned |
| Upload integrity | Ciphertext-only, unique destinations, manifest last, full archive+metadata readback; simulated transport tests passed |
| Schedule activation | New coordinator blocks before dump without bound real recovery evidence and owner approval; not installed/enabled |
| Safe retention | Preserve-all remains active; non-destructive evidence-gated eligibility planner implemented/tested; no deletion supported |
| Encrypted restore | Actual verified backup encrypted/decrypted and restored on isolated DB with ephemeral test key; PASS |
| Production health/integrity | PASS; no service restart, schema or business write |

Files added/updated: `ops/phase10/backup_proposal.py`, `backup_safety.py`,
`backup_schedule.py`, off-server/activation JSON examples, recovery requirements,
uninstalled backup service drop-in; operational restore helper and new synthetic
backup-storage tests. No application runtime/API/frontend/financial code changed.

### Security properties

Encryption config requires a protected full approved fingerprint and private owned
keyring. The scheduler refuses private recovery keys, revoked/expired/disabled or
wrong-purpose/mismatched recipients; GPG still enforces trust. No actual key was
printed, logged, committed or provisioned. Temporary test key material was scoped
to the isolated drill and removed by its cleanup; original backups remain intact.

The proposed SFTP adapter has strict host-key checking, dedicated known_hosts and
identity paths, no password/agent fallback, cleared client environment/config and
no remote shell/delete commands. It refuses private/loopback/known production-VPS
addresses, but owner must still verify physical hosting independence. It never
overwrites an earlier attempt and writes no success receipt on failed/mismatched
readback. No real network upload was performed. SFTP alone is not immutable: the
actual destination needs independently administered retention/snapshot protections.

Coordinator approval binds recipient, remote-config hash, real package/archive,
off-server identity/readback and successful isolated restore/control-baseline
evidence. It requires root-private ownership, explicit owner attestations and
expiry, serializes jobs and fails nonzero without printing client/secret details.
Only after actual encryption AND remote readback can it report whole-job success.
This is an uninstalled replacement ExecStart proposal for the existing service,
not another backup service/system. No real activation record exists.

Retention is intentionally read-only: explicit age policy, at least two recent
verified packages protected; each eligible package must have valid ciphertext
hash and matching complete off-server/full-restore receipts. Unknown/unverified,
legacy, partial, unsafe-permission, symlinked, altered, wrong-database or future
evidence is preserved. No recursive/file delete or quarantine was performed or
implemented. Eligibility does not reclaim storage; cleanup needs separate review.

## Test results and actual recovery boundary

- **62 tests +48 subtests passed**, zero failures/errors/skips,3 existing Pydantic
  warnings, on existing isolated test databases and temporary synthetic files.
- Covers strict config/identity permissions, pinned host checks, transfer/readback
  success and corruption/failure contracts, local-VPS refusal, recipient misuse,
  preservation/retention guards, activation evidence binding and pre-dump refusal,
  plus existing Platform Admin/MFA/billing regressions.
- Off-server tests use a **simulated SFTP transport**, not a real external server.
  Real DNS/host-key/account/access/immutability/off-server recovery remain pending.
- An initial unit test exposed plan abortion on a symlink; fixed to preserve and
  exclude it. The final suite passes. No unsafe path was deleted.
- Full real-dump encrypted restore used source backup SHA
  `390e5673e8ec4a0e81706aa9a0bd8874e37d0f4d8e405f15981de39028469965` and
  a temporary test-only recovery key. Public-only encryption passed; putting the
  private key in the scheduler keyring was rejected. Corrupt ciphertext rejected.
  No plaintext recovery file created and no production connection by this drill.
- New application-inaccessible disposable restore target:
  `apexretail_backup_encrypted_20261021t105750538528`.
  **34 tables /890 rows**, original hashes, financial/inventory controls,
  ownership/ACLs and revision matched. Same-VPS isolated drill is **not** off-server
  disaster recovery or real custodian acceptance. No synthetic result was promoted
  into production activation proof.

## Production verification

API health `ok:true`; POS200; Backoffice200. API/watchdog/backup timer remain active.
No restart, service/config change, Phase10 migration, domain activation, APK build,
test sale or queue operation. Read-only comparison to the fresh verified backup:
original hashes, numeric controls and owner/ACLs unchanged; five open shifts
preserved; mandatory shift enforcement OFF; revision remains p5h.

No full frontend/application rebuild was needed: application source unchanged.
Earlier complete regression evidence remains separate and was not counted again.
Private evidence is retained under:
`/root/apexretail-pos/backups/phase10-backup-encryption-preparation-20261021/`.

## Inputs and approvals still required

1. **Real encryption recipient/custodian:** provide non-secret identity and verified
   fingerprint; provision the actual public key through a protected channel.
   Approve independently held encrypted private-key escrow, recovery access and
   key rotation/lifetime. Never send private keys or passwords through chat.
2. **Actual off-server destination:** choose provider/hostname/account/path and
   verify independent hosting, host identity, restricted upload permissions,
   immutable retention/snapshots and capacity. No provider/account was invented.
   SFTP is the prepared option; another provider needs its adapter reviewed/tested.
3. **Real end-to-end acceptance:** approved one-off backup with consistent baseline,
   upload, independent retrieval, actual custodian-key decrypt/full isolated
   restore, failure/alert tests and agreed recovery objectives. Secret/config/media
   recovery must be covered separately. Produce actual hash-bound private evidence.
4. **Retention/monitoring policy:** approve age/count/tier rules, capacity and failed-
   backup alerts. Current preserve-all stays in force; do not delete history.
5. **Explicit activation:** only after1–4 pass, approve exact protected code/config
   installation and the reviewed existing-service drop-in. Obtain owner-approved
   expiry and bind the real evidence in the private activation record. Then verify
   a complete scheduled run. **No scheduler change or remote upload was made now.**

This task prepares the software and proves the isolated mechanism. It cannot
establish real key custody or create an unspecified external storage account.
**Scheduled encrypted backups: INACTIVE / external acceptance and approval PENDING.
Phase10 and admin.apexpos.cloud: NOT DEPLOYED/ACTIVATED.**
