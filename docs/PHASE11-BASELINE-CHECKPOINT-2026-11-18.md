# Phase 11 baseline reconciliation checkpoint

Date: 18 November 2026.

## Candidate and provenance

Branch: `phase11/baseline-reconciliation`.

- Base release: `9f331b88a4affd82cc4c1e58cf175f93b958f5e6`.
- `4d992ef`: preserved audit and frozen seven-file POS login fix.
- `c0caa39`: preserved three backend PyJWT application changes, runtime lock, compatibility script, three changed test files and required legacy synthetic-token fixture.

The operator copied the nine explicit backend files from `/tmp/apexpos-phase7f` into `/tmp/apexpos-phase11` using byte comparisons before commit. This agent observed the command and successful push through user-provided terminal screenshots. No fresh independent comparison with installed runtime files or deployment manifest was performed in this chat.

## Verification observed

The operator ran the supplied isolated test block on Linux using CPython 3.10. A new temporary virtual environment installed `backend/requirements-runtime.lock`. Commands ran from the temporary directory with `env -i`, synthetic settings and a deliberately unreachable database URL; production environment variables were excluded.

- Locked dependencies installed successfully, including PyJWT 2.15.1.
- `python -m pip check`: no broken requirements found.
- `python -m unittest discover -s <backend>/tests -p test_final_jwt_dependency_guards.py -v`: 5 tests passed.
- `python -m unittest discover -s <backend>/tests -p test_entitlement_key_rotation.py -v`: 6 tests passed.

These are 11 observed backend tests, including legacy token compatibility, algorithm/signature rejection, explicit offline-expiration recovery behavior, dependency-chain assertions, entitlement rotation, tenant binding, expiry and grace policy. They do not certify endpoint authorization or database integration.

PyJWT emitted key-length warnings for synthetic negative-test inputs (HS512 wrong-algorithm case and an HS256 algorithm-confusion case). The suites passed. These warnings do not establish the length or safety of production secrets, which were not inspected.

The earlier audit separately records 14 focused frontend tests and frozen-source hash checks; those were not rerun in this checkpoint. No aggregate whole-system pass is claimed.

## Remaining baseline gates

1. Independently compare candidate application hashes and dependency identity against the installed runtime and retained deployment manifest; source-copy provenance alone is insufficient.
2. Check all candidate source, test and tooling dependency references for remaining python-jose imports. Default-branch GitHub search is not a branch-wide verification.
3. Verify the changed clone-compatibility script and fiscal test under suitable isolated fixtures. The fiscal module contains database-backed tests; do not run its entire suite against inherited configuration.
4. Establish reproducible POS/Backoffice builds and source/artifact metadata; retain offline data compatibility.
5. Obtain metadata-only deployed schema identity through reviewed read-only access before planning migrations. No live schema identity was queried here.
6. Perform broader tenant, permission, finance, migration and recovery acceptance with disposable synthetic infrastructure.

## Release decision

Backend compatibility changes are preserved with a narrow passing isolated regression subset. Baseline reconciliation and production readiness remain incomplete. Super Admin remains NO-GO under the existing recovery/security/migration gates. No production deployment, migration, service restart or credential change was performed by this work.

## Autonomous continuation evidence

The earlier observations above remain historical. Independent reconciliation, isolated builds, schema metadata and subsequent security development are now recorded in [PHASE11-PROGRESS-2026-11-18.md](PHASE11-PROGRESS-2026-11-18.md), with commands, exact implementation commits and retained artifacts. Baseline reconciliation commit: `e9acf7d`; security increments: `e4eec3c`, `fe2a522`, `efd9b38`. The candidate now contains an isolated-tested additive p11a migration; production was inspected at p10a and was not migrated. Focused baseline gates are satisfied within the recorded scope; broad release/tenant/finance/recovery/hardware acceptance remains incomplete. Push is blocked by missing HTTPS GitHub credentials. Super Admin and production remain NO-GO.

## Identity continuation checkpoint

Operator confirms push through `10200e2`. Subsequent local increments: `a1b5e5e` (policy assessment/unsupported User gate; expanded to 251 operations in fbba470), `935e968` (remembered browser sessions), `b4b1111` (password recovery with encrypted test sink), and `fbba470` (single-use handoff and isolated acceptance). See the progress report for exact commits, commands, 92-test combined run, final 17-test race/role run, browser/concurrency evidence and limits. Isolated databases reached p11d via 54 source revisions; production was not migrated. Push from this agent still lacks HTTPS authentication. Every rollback must retain user/session revocation, reset/refresh/handoff one-use checks and frontend context replacement. Super Admin and production remain NO-GO.
