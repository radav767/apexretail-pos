# Phase 2 failure recovery

The Phase 2 deployment is guarded from `c2phase1inventory` to
`d3phase2discount`. The migration only adds nullable `sales.discount_amount`.
The deployment script never restores a database or runs `alembic downgrade`
automatically. Retain the entire timestamped directory under
`/root/apexretail-pos/backups/phase2-production`, every test database and all
published APKs until an incident owner approves cleanup.

The first authorized attempt on 2026-09-09 stopped during APK preflight before
any database dump, asset backup, service stop, migration, or publication. The APK
was valid; `zipinfo | grep -q` produced a false failure under `pipefail` when the
matcher exited before `zipinfo`. The corrected preflight writes the complete APK
listing to a root-only evidence file before matching required entries. Signer and
badging producers are also fully consumed before their output is parsed. Retain
the failed-attempt evidence directory beginning with `20260909T114350Z-b7e80d1c`.

The renewed deployment completed migration, aggregate checks, service recovery,
asset and APK publication, public-file checks, and the authenticated Dashboard
request before reporting a late nonzero status. The final verifier attempted to
assign to the readonly `DASHBOARD_COMPANY_ID` shell variable; its database client
also required the application's `postgresql+asyncpg` URL to be adapted to the
synchronous `postgresql` driver for `psycopg2`. The finalizer now passes the ID as
`EXPECTED_DASHBOARD_COMPANY_ID` and invokes an independently mocked and tested
Python verifier. This class of failure does not by itself justify redeployment,
rollback, service restart, or republication: confirm the production revision,
health, published bytes, and preserved Dashboard response before deciding that
only finalization failed. Retain the `20260909T151202Z-e45651f...` evidence.

## First response

Stop the deployment command after any failure. Record its exit status and output,
then inspect without changing state:

```bash
cd /root/apexretail-pos
git rev-parse HEAD
git status --short
sudo -u postgres psql -X --no-psqlrc -d apexretail_pos -qAt \
  -c 'SELECT version_num FROM alembic_version;'
systemctl status apexpos --no-pager
curl --fail --silent --show-error http://127.0.0.1:8000/api/health
curl --fail --silent --show-error https://api.apexpos.cloud/api/health
```

Do not delete or edit evidence. Confirm the database dump is nonempty, mode 600,
has its recorded SHA-256, and passes `pg_restore --list` before considering it a
usable recovery source. A dump that fails any check must not be restored.

## Failure before service stop

Production has not been migrated or republished. Leave the existing backend and
web roots in place, correct the preflight problem in a reviewed commit, rerun all
validation, and request fresh approval. Retain the generated backups and evidence.

## Failure after service stop but before migration

The database remains at `c2phase1inventory`. Start the existing service and check
both health endpoints. This is service recovery, not database recovery:

```bash
systemctl start apexpos
curl --fail --silent --show-error http://127.0.0.1:8000/api/health
curl --fail --silent --show-error https://api.apexpos.cloud/api/health
```

Do not restore the database merely because the service was stopped.

## Migration or backend-health failure

Determine the actual Alembic revision and inspect `sales.discount_amount`. Do not
assume a failed command rolled back, and do not rerun the full deployment until
the state is understood. Prefer a reviewed forward fix. Because the Phase 2
migration is additive, the previously deployed backend may tolerate the new
column, but that must be verified from the recorded commit and tested before any
checkout or service restart.

Database restore or `alembic downgrade c2phase1inventory` requires a separate,
explicit incident decision after checking for post-backup writes. Either action
can discard production data created after the snapshot. The deployment script
must never be modified to perform either action automatically.

## Asset-publication failure

If backend health passed but POS or Backoffice publication failed, leave the
database at `d3phase2discount` and keep the backend running. Compare each public
tree with the timestamped `pos-assets` and `backoffice-assets` backups. Restore a
web tree only after an explicit operator decision, using `rsync --archive
--delete --delay-updates --chmod=D755,F644`. Backoffice restoration must retain
`--exclude='/downloads/***'` so no APK or download is removed.

Never overwrite or delete a published APK. If an APK URL fails, verify its local
mode, signer, archive integrity and SHA-256, then correct only the publication or
Nginx issue. Keep the Phase 2 release candidate available until final production
acceptance is complete.

## Recovery completion

Record the chosen recovery action, Git commit, database revision, service state,
local/public health responses, public POS and Backoffice results, APK URL and
checksum. Retain database dumps, asset snapshots, aggregate CSV files, public
Dashboard response and command logs until cleanup receives separate approval.
