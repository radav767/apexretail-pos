# Phase 3 detached staging recovery

## Root cause

The stopped production attempt invoked `python -m unittest discover` directly
inside the detached release-candidate worktree. Git does not copy the ignored
`backend/.env` into a worktree. Importing `app.db.session` therefore asked
Pydantic for `DATABASE_URL` and `JWT_SECRET`, and test discovery failed before
the complete suite could run. A follow-up invocation supplied an intentionally
unavailable socket URL but did not provision PostgreSQL, so database-backed
tests waited for a connection instead of providing a usable staging run.

Neither failure reached a production migration, service stop, asset publication,
database dump, or APK operation.

During pre-commit testing of the correction, an initial sequencing defect ran
the first `createdb` before `PGHOST` was exported. It appears to have created the
empty test-prefixed database `apexretail_phase2_test_fresh` on the host cluster.
The production application database remained at `d3phase2discount` and was not
migrated. The unexpected database is retained pending a separate cleanup
decision; recovery must not silently delete it. The corrected command always
passes the protected temporary socket and `postgres` user directly to
`createdb`, independent of ambient environment variables.

## Correct staging invocation

Run the committed validator from a clean detached worktree. Do not copy or link
`backend/.env` into that worktree:

```bash
git worktree add --detach /tmp/apexretail-phase3-production-stage COMMIT
ln -s /root/apexretail-pos/backend/venv \
  /tmp/apexretail-phase3-production-stage/backend/venv
(cd /tmp/apexretail-phase3-production-stage && \
  bash backend/scripts/validate_dashboard_phase3.sh)
```

The validator refuses an `.env`, removes inherited application database and
secret variables, generates a test-only JWT secret, creates a unique protected
PostgreSQL cluster under `/tmp/apex-phase3-validation-*`, disables TCP, and
supplies explicit URLs for a test-prefixed database. Before Alembic runs, it
requires `pg_isready` and verifies the connected database name, Unix-socket
transport, and temporary data-directory identity. Missing or unavailable
isolation exits before migrations; it cannot fall back to the application
configuration.

The temporary server is stopped by the exit trap on success or failure. Cleanup
must report that neither `postmaster.pid` nor the PostgreSQL socket remains.

## Renewed production preflight and backup plan

A future production attempt requires fresh explicit approval for its exact
commit. Before mutation, rerun detached staging, verify the tracked tree and
stash identity, then create a new timestamped custom-format `pg_dump` plus POS,
Backoffice, configuration metadata, APK inventory, and current-state backups.
Use root-only directories/files, validate the dump with `pg_restore --list`,
checksum every payload artifact, and verify the checksum manifest. Only after
all checks pass may the backend be stopped and the reviewed
`d3phase2discount -> d4discountcomponents` migration be considered.

No APK build or publication belongs to the Phase 3 web deployment.
