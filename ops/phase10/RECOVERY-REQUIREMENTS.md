# Backup encryption and recovery — prepared, not activated

The existing scheduler still uses the corrected legacy plain-SQL job. Its unsafe
recursive deletion command has now been removed; preserve-all is the policy until
the owner approves narrowly scoped retention. The encrypted replacement remains
uninstalled. Do not claim that current routine backups are encrypted.

## Prepared storage and required owner input

- `/root/apexretail-pos/backups/scheduled-production` is root-owned0700 and outside
  every web root. The proposed encrypted job uses umask077, files0600, a custom
  pg_dump stream, authenticated GPG encryption and atomic ciphertext publication.
- Owner must provide/approve an independently verified public encryption-key
  fingerprint, its trust verification and a protected public-key-only backup
  keyring. Never invent a production recipient or use an always-trust override.
- The private decryption key belongs in an approved encrypted/offline recovery
  store, not the scheduler, repository, web root, chat, command arguments or logs.
  Verify recovery access by authorized personnel; preserve old decryption keys
  for the full lifetime of backups encrypted with them.
- Approve encrypted off-host replication and recovery-host access, capacity
  alarms, retention and any eventual deletion separately. Preserve existing
  history by default. Hashes and ciphertext on the same compromised host alone
  are not complete disaster recovery or independent authenticity assurance.
- Proposed config remains `backup.json.example` with no valid recipient. Do not
  install/enable the replacement until an actual approved-key restore passes.

## Reviewed restore procedure

1. Use a restricted recovery environment and obtain the approved manifest/checksum
   from its trusted protected source. Verify the ciphertext SHA-256 before use.
2. Retrieve/unlock the authorized decryption key using the recovery store/agent;
   do not put passphrases in command arguments, environment dumps or shell tracing.
3. First decrypt to `/dev/null` and require success to check cryptographic
   integrity before attempting a restore. Never treat a partial plaintext stream
   or a successful last command in a failing pipeline as a verified backup.
4. Create a **new** allowlisted disposable database; never overwrite an existing
   database. Revoke PUBLIC/application CONNECT/TEMPORARY and verify application
   isolation. Use the schema-owner role, not elevated application DDL privileges.
5. With `pipefail` enabled, stream a second successful decryption into
   `pg_restore --exit-on-error --single-transaction` for the isolated target.
   Check both decrypt and restore exit codes. Do not create a plaintext recovery
   file unless separately necessary and protected0600 in a private0700 directory.
6. Compare revision, all original table/column hashes, numeric control totals
   grouped by company/currency, ownership/ACLs, shifts and safety flags against
   the snapshot-consistent baseline. Run isolated compatibility/security checks.
7. Retain private evidence and mark that archive restore-verified only after all
   checks pass. Clean up test-only keys using the test's scoped cleanup; never
   delete historical backup keys or archives as part of this procedure.
8. A successful disposable restore is **not** authorization to restore production.
   Before any disaster recovery, reconcile newer financial writes and queues,
   obtain owner approval, and use a reviewed forward-recovery/cutover procedure.

The new `verify_phase10_encrypted_restore.py` proved an encrypted/decrypted full
restore of the verified backup and rejected altered ciphertext, using a temporary
test-only key. It never connected to production, never provisioned a real key and
created no plaintext recovery file. The source backup remains intact. This proves
the mechanism, not production key custody, off-host resilience or real-key recovery.

## Prepared off-server and activation tooling (still uninstalled)

`backup_safety.py` provides a **proposed SFTP delivery option**, not a provisioned
backup server. `offserver.json.example` intentionally has no host, account,
destination or pinned host identity. Owner must choose the provider/destination;
if object storage is chosen instead, implement/test that adapter before activation.
Do not repurpose production SSH credentials or silently choose a provider.

The SFTP option requires an independently verified dedicated host-key fingerprint,
one-entry known_hosts file and protected upload-only identity. It uses strict host
checking, no password/agent fallback, no ambient SSH config and no remote shell.
It refuses private/loopback addresses and this production VPS's known public IP;
these checks alone do not prove physically independent storage. Owner must verify
hosting independence, capacity, access controls and recovery availability.
Only encrypted archives and minimal hash/size metadata are uploaded. Unique
attempt directories avoid overwrite; assets first/manifest last; full downloads
must match before a private success receipt is written. No remote deletion exists.

SFTP by itself is **not immutable storage**: a compromised upload credential might
delete data outside this client's behavior. Require independently administered
immutable snapshots/retention locks or a provider with suitable object-lock
controls. Test rejection of unauthorized access/deletion on the real destination.
Do not present simulated transport tests as proof of an actual off-server copy.

`backup_schedule.py` is the proposed coordinator for the existing service, not a
new scheduler. It serializes execution, validates approved custody/storage and
matching real encrypted/off-server/full-restore evidence **before any dump**, then
requires successful encryption and full off-server readback. Missing/expired
approval or changed recipient/remote configuration blocks it. It never creates an
approval, enables a timer or prunes history. The uninstalled systemd drop-in now
points to this coordinator, not the local-encryption-only helper.

`backup-activation.json.example` is deliberately disabled. An authorized operator
may populate a root0600 approval only after the owner approves the actual recipient,
custody, separate storage and actual recovery. Bind it to the recipient, remote
config checksum, real verified archive and private package evidence, with an
owner-selected expiry (at most one year). Do not copy synthetic test receipts into
production proof or manufacture restore evidence. A recovery receipt must record
the actual archive hash, isolated target and successful baseline comparison.
The public-keyring check refuses secret recovery keys and unusable recipients.

## Retention safety

Live policy remains **preserve all**; no cleanup job is installed. The prepared
`retention-plan` command is read-only and needs an explicit age policy. It selects
only checksum-valid, encrypted, known-format packages with bound off-server
readback and successful isolated full-restore receipts. It protects at least the
two most recent verified packages. Unknown, legacy, partial, corrupt, linked,
foreign, future-dated or mismatched evidence is preserved/excluded.

The output is eligibility for **separate approval**, not a deletion command. No
local/remote delete, move or recursive pruning is implemented; it does not free
space. Agree the daily/monthly/yearly policy, key lifetime, immutable remote
retention and capacity/failure alerts before considering any reviewed cleanup.
Never apply age-only `find`, filesystem timestamps alone or wildcard recursive
deletion to the existing history.

## Activation sequence requiring owner approval

1. Select real key custodian and provider, verify fingerprints independently and
   provision protected public-only encryption/upload configuration. Keep private
   recovery keys on an approved recovery system, not in the scheduler.
2. Perform an authorized one-off snapshot-consistent backup/control baseline and
   encrypted upload using the real configuration. Independently retrieve that
   exact remote archive and manifest on the recovery environment.
3. Verify hashes and cryptographic integrity before restoring into a new isolated
   application-inaccessible database; compare the original snapshot baseline.
   Include recovery of required roles/config/media/entitlement/MFA key material
   under separate protected custody, not just the database. Do not overwrite live
   records or test by restoring production.
4. Test wrong/missing keys, unavailable remote server, mismatched ciphertext,
   rejected host identity, failed dump/upload and alert delivery. Establish
   approved recovery-point/time objectives and restore-drill cadence.
5. Record actual private evidence, obtain explicit activation approval, review the
   exact code/config hashes, install protected code and then change the existing
   service ExecStart under that approval. Preserve its schedule/history and
   validate a complete run. No such installation/change happened in this task.
