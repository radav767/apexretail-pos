# Scheduled production backup target correction

Completed 21 October 2026 UTC. Scope: one database argument only; **Phase 10 not deployed**.

## Change applied

`/root/apexpos-tools/backup.sh`:

```diff
-sudo -u postgres pg_dump apexpos > /root/backups/$DATE/apexpos.sql
+sudo -u postgres pg_dump apexretail_pos > /root/backups/$DATE/apexpos.sql
```

The legacy `apexpos.sql` output filename is intentionally unchanged: only the database target was authorized. The script remains root:root0755. Its original copy is preserved. No application/runtime source, APK, database schema/record, environment, Nginx file, service unit, timer unit or schedule was changed. No service restarted. An exclusive deployment lock covered the edit and was verified released.

Script SHA-256 before: `5333227e9257331764f894b7acc1eadebb1112329a492ce67ad81613ed6641d5`.
After: `ac0406fdbcd088eb29db9dd425b580c71adca37ad4558c38c7e45736fefd47ff`.
Byte comparison confirmed the target substitution was the sole change. `bash -n` passed.

The active systemd service still executes this same script. Unit hashes unchanged:

- service: `5b002a4eb6d4ab4bc08c4f54983654ae6d4ef3332334f3ba96d8fddf54982f35`
- timer: `c2660c48f74b50bb7e63dfac87fafdb388e92ac54326ffb5e2a9f9f2b34f074d`

Timer remains active, scheduled daily02:00 UTC; next run observed 22 October02:00 UTC. Backup service was idle during preparation. No daemon reload is required for a script-content change.

## Fresh backup BEFORE correction

Private persistent evidence directory:
`/root/apexretail-pos/backups/backup-target-correction-20261021T101229Z/`

`before-custom/apexretail_pos.dump`: **241,780 bytes**.
SHA-256: `390e5673e8ec4a0e81706aa9a0bd8874e37d0f4d8e405f15981de39028469965`.

Read-only production snapshot, custom-format pg_dump with the same exported snapshot as the content/control baseline. Archive catalog validated. Full transactional restore passed in new isolated database:
`apexretail_backup_target_before_20261021t101405917964`.

A first rehearsal attempt stopped at disposable database creation due to test-harness transaction handling, before creating/restoring a database. It made no production changes. The harness was corrected and the final backup and restore passed before editing the installed script.

## Corrected plain SQL dump verification

`after-plain/apexretail_pos.sql`: **376,836 bytes**.
SHA-256: `fda4b4954c43617dd3fae8778f4e8c86dfe03aaccef527cd4d23cc9eae4e7800`.

The corrected pg_dump target/default plain format was exercised as postgres. The test adds `--snapshot` for consistency with its read-only comparison baseline; that test-only option is not an installed job change. Full restore with psql `ON_ERROR_STOP=1 --single-transaction` passed in new isolated database:
`apexretail_backup_target_after_20261021t101505501929`.

Both clones deny CONNECT/TEMPORARY to PUBLIC/apex_user; no nonsuperuser login can connect. Neither was a reset or overwrite. They are disposable restore evidence, not another application or staging deployment. No migration or application financial transaction was run.

Both restores matched **34 historical tables / 890 rows**, original-column content hashes, exact company/currency-grouped numeric controls, table ownership/ACLs, original revision and schema privilege baseline. Independent before/after production snapshots matched as well. All five open shifts preserved; mandatory enforcement OFF. Production remains **apexretail_pos**, revision **p5h_runtime_write_permissions**.

Dump/evidence files0600 inside private0700 directories; the enclosing persistent directory is root0700. Existing `/root/backups` file inventory, sizes and modification timestamps were identical before/after. No historical backup was modified or deleted.

## Scope boundary and remaining routine-backup risks

**The complete legacy shell script was NOT invoked**, because its existing retention step recursively deletes old directories and the owner required all backups preserved. The corrected database dump and full restore, not the unrelated copy/retention steps, were verified. A timer result alone is not proof of a verified restore.

As explicitly limited to changing the target, this work does not fix the existing plaintext output, permissive inherited backup-directory/file defaults, stale backend/POS copy paths, lack of fail-fast checks or unsafe deletion-based retention. The timer still contains that existing retention policy. These require prompt separate approval before claiming the overall scheduled-backup system is secure. No unapproved encryption key, retention policy or backup redesign was introduced.

The previously prepared encrypted fail-closed proposal remains uninstalled. Approve the verified public-key recipient/trust, encrypted recovery/off-host storage, private permissions, accurate asset/config sources, failure monitoring and a narrowly scoped retention policy. A real encrypted database restore must pass before accepting that replacement. Keep all existing history unless pruning is separately authorized.

## Production health after correction

- POS HTTPS200; Backoffice HTTPS200.
- API health `ok:true`, app ApexRetail POS.
- API service, health timer and backup timer active; no restart.
- Nginx main/POS/Backoffice configuration hashes unchanged.
- No application code, Android APK, local storage, offline queue, financial value or schema altered.

No broad application regression suite was repeated: application code is unchanged. Operational checks were backup/restore/content validation, installed script syntax/diff, timer/service verification, history inventory comparison and read-only production health/integrity checks. `verify_backup_target_correction.py` is an operational verification helper, not a runtime application change.

## Next requirements for admin.apexpos.cloud

The hostname still fails HTTPS certificate-name validation (curl60): its current certificate does not cover admin.apexpos.cloud. Do not bypass TLS verification.

Before activation, separately approve:

1. Protected Phase 10 runner installation plus exact installed-context disposable rehearsal. Existing candidate runtime remains `932557e3abca1a2fa046b2d04d0d6f8c6d4bcc35`.
2. Coordinated maintenance with fresh backup/baselines, explicit terminal queue clearance/open-shift preservation, safe database-specific write freeze and exact ACL restoration; apply all14 pending migrations p5h→p10a only under that approval.
3. Secure MFA key creation/escrow and reviewed EnvironmentFile integration; initial platform administrator identity, private interactive password provisioning, authenticator enrollment and recovery acceptance. No admin or secret was created now.
4. Dedicated admin certificate/renewal and reviewed ACME/final Nginx vhost; validate before a separately approved graceful reload, preserving existing host routes.
5. Exact backend/console artifacts, protected snapshots and coordinated deployment/forward-recovery procedure. No Phase 10 activation is authorized by this backup correction.

**Target correction: COMPLETE. Corrected database dump and isolated restore: PASS. Phase 10 production activation: NOT DEPLOYED / approvals pending.**
