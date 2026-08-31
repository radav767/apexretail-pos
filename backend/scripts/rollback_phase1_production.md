# Phase 1 production rollback and recovery

This runbook is deliberately manual. The deployment script never restores a database or runs an Alembic downgrade after a partial failure. Preserve the failed state and evidence until the incident owner chooses a recovery path.

## Fixed production identity

- Repository: `/root/apexretail-pos`
- Database: `apexretail_pos`
- Pre-deployment revision: `b8e51d8f4a21`
- Phase 1 revision: `c2phase1inventory`
- Backend service: `apexpos`
- Deployment evidence: `/root/apexretail-pos/backups/phase1-production`
- POS web root: `/var/www/apexretail-pos`
- Backoffice web root: `/var/www/apexpos-backoffice`
- APK directory that must be preserved: `/var/www/apexpos-backoffice/downloads`

Never paste `.env`, database URLs, JWT secrets, Paynow keys, entitlement private keys, or command output containing them into an incident log.

## First response after any failure

1. Stop and record the exact failed step, UTC time, deployed Git commit, backup path, inventory-evidence path, and current service state.
2. Do not rerun the deployment blindly. Do not run `alembic downgrade`, `pg_restore --clean`, or overwrite `apexretail_pos`.
3. Inspect only non-sensitive state:

   ```bash
   cd /root/apexretail-pos
   sudo -u postgres psql -X -Atqc 'SELECT current_database(), version_num FROM alembic_version;' apexretail_pos
   systemctl status apexpos --no-pager
   journalctl -u apexpos -n 200 --no-pager
   curl --fail --silent --show-error http://127.0.0.1:8000/api/health
   curl --fail --silent --show-error https://api.apexpos.cloud/api/health
   ```

4. Verify the named backup without restoring it:

   ```bash
   stat -c '%a %U:%G %n' /root/apexretail-pos/backups/phase1-production/apexretail_pos_before_phase1_TIMESTAMP.dump
   sudo -u postgres pg_restore --list /root/apexretail-pos/backups/phase1-production/apexretail_pos_before_phase1_TIMESTAMP.dump >/dev/null
   ```

The backup mode must be `600`. Replace `TIMESTAMP` only after copying the exact filename from the deployment output.

## Choose the recovery path from the failure point

### Failure before Alembic starts

Production remains at `b8e51d8f4a21`; no database restore is appropriate. If the script stopped `apexpos`, review its logs and start it:

```bash
systemctl start apexpos
systemctl is-active --quiet apexpos
curl --fail --silent --show-error http://127.0.0.1:8000/api/health
```

Correct the packaging, test, backup, or Class A precondition failure before scheduling a new attempt.

### Failure during or after migration

Keep the backend stopped until the current revision and schema state are known. Alembic/PostgreSQL transactional DDL may have rolled back the failing revision, but never assume that it did.

```bash
sudo -u postgres psql -X -Atqc 'SELECT version_num FROM alembic_version;' apexretail_pos
journalctl -u apexpos -n 200 --no-pager
```

Prefer a reviewed forward fix when the database is at `c1phase1refunds` or `c2phase1inventory`. The `c2phase1inventory` downgrade is intentionally non-destructive, and downgrading `c1phase1refunds` removes Phase 1 tables/columns; neither operation reconstructs the exact pre-deployment state.

If an incident owner authorizes database recovery, first restore the pre-deployment dump into a newly created, strictly named recovery database and validate revision, row counts, Class A inventory aggregates, and application compatibility there. Only then write and approve a separate outage/cutover plan. Do not point Alembic or the application at the recovery database until its exact name and purpose have been independently checked.

Before any approved production restore, take another permission-600 dump of the failed production database. Never restore directly over the only copy of the failed state.

### Backend code or health failure with a valid `c2phase1inventory` database

Do not downgrade the database merely to address an application error. Re-deploy a reviewed forward fix, or check out the recorded pre-deployment commit only after confirming that its backend tolerates the additive Phase 1 schema. Then restart and verify both health endpoints.

### Static asset failure

The deployment output gives timestamped POS and Backoffice asset backup directories. Inspect the exact paths before copying. Restore only after approval:

```bash
rsync --archive --delete /root/apexretail-pos/backups/phase1-production/pos-assets-TIMESTAMP/ /var/www/apexretail-pos/
rsync --archive --delete --exclude='/downloads/***' /root/apexretail-pos/backups/phase1-production/backoffice-assets-TIMESTAMP/ /var/www/apexpos-backoffice/
```

The Backoffice command must retain `--exclude='/downloads/***'`. Verify that `/var/www/apexpos-backoffice/downloads` and every prior APK still exist before and after the copy.

### APK publication failure

Never overwrite the previous APK. Installed APKs cannot be remotely rolled back by deleting a download. Keep the new versioned APK as incident evidence unless the incident owner explicitly approves removing it, and restore UI links to the prior known-good filename if a link changed. Verify the chosen APK's signer, SHA-256, and public URL before announcing it.

The current Android package uses the Android debug signer and declares `versionCode 1` / `versionName 1.0`. A future release-keystore and monotonically increasing version-code migration needs a separate signing and upgrade plan; do not improvise it during rollback.

## Post-recovery verification

Verify all of the following before closing the incident:

- PostgreSQL and `apexpos` are active, and local/public API health succeeds.
- The database identity and Alembic revision match the chosen recovery path.
- Inventory movement count/quantity and canonical product physical quantity, cost value, and retail value reconcile to retained evidence.
- No duplicate `(company_id, branch_id, product_id)` balance keys exist.
- POS and Backoffice pages load, and the downloads directory plus all previous APKs remain present.
- Login, shop/terminal selection, takeover, duplicate receipt marking, approved non-financial refund, disposable product archive, and disposable terminal archive smoke checks pass.
- No real payment is created. Do not repeatedly call Paynow checkout while its network case remains pending with Paynow.

Record the final Git commit, database revision, service status, public health result, APK URL/SHA-256, and the recovery decision. Retain all dumps and evidence until the incident owner explicitly approves cleanup.
