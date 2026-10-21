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
