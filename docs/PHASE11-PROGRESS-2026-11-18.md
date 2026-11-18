# Phase 11 development execution record — 18 November 2026

Branch: `phase11/baseline-reconciliation`. Starting checkpoint: `46252e4497829213ff6e1e0e4a763e641f064b57` (clean). No AGENTS.md found in this workspace or its ancestors; `.agents` and `.codex` are empty. Audit and baseline checkpoint read before implementation.

## Baseline reconciliation

Evidence: `artifacts/phase11-baseline-20261118/`.

- Independently compared SHA-256 maps of all **194** candidate `backend/app/**/*.py` files against `/opt/apexpos-migration-runners/phase7-onward-remediated-20261022/backend`, selected by installed `60-phase7-onward.conf`: identical maps. All application entries in retained `PAYLOAD.sha256` match installed files. This proves configured source identity, not process liveness.
- `backend/requirements-runtime.lock` matches installed source. All **37** pinned distribution versions match both the configured runtime's dist-info metadata and isolated CPython 3.10 environment. Did not execute or modify the production interpreter. Lock SHA-256: `34b040afe98bc63ddc01c7e254472a6dc9a1fda2f3eeead8d9c7f65f8dcbc554`.
- AST-scanned every backend Python source/test/script: no `jose` imports remain. Text matches only identify the preserved synthetic legacy-token fixture and negative dependency assertions.
- All seven frozen POS source/test/script hashes still match `/root/apexretail-pos/artifacts/pos-first-login-fix-20261117/frozen-source-inputs.json`.
- Independently reran the 11 JWT/entitlement tests and `pip check`: pass. Five fiscal validation tests also passed in that database-free run. Synthetic algorithm-confusion inputs still produce the previously documented key-length warnings.
- Node **v20.20.2**, npm **10.8.2**. Locked Vite 8.1.6/plugin-react 6.0.3 require `^20.19.0 || >=22.12.0`; Capacitor CLI requires `>=20.0.0`. Requirements satisfied.
- Archived tracked POS/Backoffice source from `46252e4` to `/tmp/apex-phase11-build-xijhpj7t`. Ran `npm ci --no-audit --no-fund --engine-strict` in each real directory with `env -i`, separate npm cache; never installed against shared/symlinked node_modules. Initial sandbox DNS failures caused npm's misleading “Exit handler never called” output; network-enabled retries installed 202 POS and 57 Backoffice packages successfully.
- Ran both `npm run build` commands twice. All dist file SHA-256 maps match between successive builds with identical inputs. POS used an ephemeral synthetic public entitlement keyring, whose private key was never written. These artifacts **must not be deployed**. Builds warn about chunks over 500 kB. This proves repeatability in one isolated environment, not cross-platform reproducibility or production keyring acceptance.
- From isolated POS copy: `node scripts/run-auth-lifecycle-tests.mjs` and `node scripts/run-entitlement-tests.mjs`: **7 + 7 pass**. No offline queues or browser storage were opened/cleared.
- Initialized a new Unix-socket-only PostgreSQL 14 cluster at `/tmp/apex-phase11-postgres-auOybQ`, port 55441. Created NOLOGIN `apex_user` there. Applied all 50 source revisions to a fresh synthetic database `apexretail_phase7c_test_phase7d`: success through `p10a_platform_management`. No production migrations.
- Reviewed `test_phase9_fiscal.py` and its Phase7D/printing fixture chain before running all **16 fiscal tests** on that database: pass, no skips. These tests establish source preparation/immutability/tenant checks, never fiscal authority acceptance.
- Hardened `verify_phase10_clone_compatibility.py`: requires explicit `PHASE10_COMPATIBILITY_DATABASE_URL`, exact disposable clone name and local socket; checks transaction_read_only before table/API checks; refuses empty owner fixtures. **Two destination-guard tests pass** without application configuration or database access.
- In the private cluster only, migrated the named compatibility database and registered two synthetic owners/businesses. Granted synthetic read access, revoked PUBLIC CONNECT. Verifier: **111 checks, two owners, zero failures**. Production OpenAPI comparison deliberately disabled; `contracts.checked=false`. Initial `.test` registration email suffix was rejected by EmailStr; fixture addresses changed to `example.com` with no email sender invoked.
- Metadata-only production inspection used the retained `schema-readonly.sql` via `sudo -u postgres psql -X --dbname apexretail_pos --file ...`. Transaction explicitly set READ ONLY, asserted it and database identity before reading. Result: read_only `on`; PostgreSQL `14.24`; `alembic_version=p10a_platform_management`; 79 public tables; constraints c=56, f=219, p=79, u=69; ROLLBACK. No business rows inspected. Initial sandbox sudo failure was retried with execution permission. This is revision identity and catalog summary, not full column/index/privilege equality certification.

### Exact test environments and commands

Isolated interpreter: `/tmp/apexpos-phase11-tests.qlfdlS/venv/bin/python` (operator-created disposable environment, independently checked). Commands start from `/tmp` unless specified, with no inherited environment:

```sh
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp PYTHONDONTWRITEBYTECODE=1 \
 PYTHONPATH=/tmp/apexpos-phase11/backend:/tmp/apexpos-phase11/backend/tests \
 DATABASE_URL=postgresql+asyncpg://synthetic:synthetic@127.0.0.1:1/phase11_unreachable \
 JWT_SECRET=synthetic-phase11-isolated-hmac-secret-123456789 APP_ENV=test \
 /tmp/apexpos-phase11-tests.qlfdlS/venv/bin/python -m unittest \
 test_final_jwt_dependency_guards test_entitlement_key_rotation test_phase9_fiscal.FiscalValidationTests -v
```

`python -m pip check` ran under `env -i`. Fiscal database tests used the same clean environment, replacing DATABASE_URL and setting APEX_PHASE7D_TEST_DATABASE_URL to `postgresql+asyncpg://postgres@/apexretail_phase7c_test_phase7d?host=/tmp/apex-phase11-postgres-auOybQ&port=55441`, then `python -m unittest test_phase9_fiscal -v`. Migration command: `python -m alembic upgrade head`, cwd `backend`, with that same synthetic environment. Clone verifier command: `python backend/scripts/verify_phase10_clone_compatibility.py` from `/tmp`, `env -i`, APP_ENV=test, PHASE10_COMPATIBILITY_DATABASE_URL pointing to the **private cluster** database `apexretail_phase10_fresh_20261021t072213`, PHASE10_COMPATIBILITY_SCHEMA=/tmp/apex-phase11-no-production-openapi.json, PHASE10_COMPATIBILITY_OUTPUT=/tmp/apex-phase11-clone-results.json. The verifier supplies its synthetic JWT secret internally. Guard tests: `python -m unittest test_phase11_clone_destination -v` with only clean PATH/HOME/PYTHONPATH.

Frontend commands used `env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp`, plus `npm_config_cache=/tmp/apex-phase11-npm-cache` for install and `ENTITLEMENT_PUBLIC_KEYRING_FILE=/tmp/apex-phase11-build-xijhpj7t/test-public-keyring.json` for POS builds. Source/lock/build artifact hashes are retained in JSON.

## Remaining acceptance and release limits

Baseline source/dependency reconciliation and focused isolated verification are complete within the scope above. Broader endpoint policy, tenant/permission/finance coverage, populated upgrade/backfill, backup/independent restore and operator/device acceptance remain required. The synthetic clone is not a restored customer database and cannot certify historical customer compatibility. No production OpenAPI semantic comparison was performed.

Proceed with audit step 2 (11A/11M security), then finance/selector foundations. Offline clock/lease trust, revocable business sessions/reset/remember me, same-account handoff and endpoint policy remain incomplete. Super Admin remains **NO-GO**, with its existing security, recovery and protected migration gates. No deployment, service/configuration changes, credential rotation, real messages/payments/providers, or APK publication is authorized. Original checkout, dirty Phase 10 worktree, frozen hotfix, offline queues and Android identity/signing remain preserved.

## Security increment 1 — fail-closed JWT configuration

Baseline commit: `e9acf7d`. Commit succeeded locally. `git push origin phase11/baseline-reconciliation` failed: `could not read Username for 'https://github.com': No such device or address`. No HTTPS credential helper or gh executable is configured. Push is externally blocked; local development continues. Git writes require execution permission because this linked worktree's index is under `/root/apexretail-pos/.git/worktrees/apexpos-phase11`.

Removed business JWT signing/verification fallback to the known placeholder. Settings and signing/decoding reject empty, whitespace-only, short and placeholder keys; HMAC floors are HS256=32, HS384=48, HS512=64 UTF-8 bytes. Empty/unsigned algorithm configuration is rejected. Settings validation hides supplied input in formatted errors. These are minimum length checks, not proof of randomness. Existing configured valid key bytes and algorithms remain unchanged; no credentials were inspected or rotated.

The legacy SECRET_KEY constant is still required by device activation/identity hashing. Its bytes are deliberately preserved so existing tombstones/activation identities remain usable. It is no longer a JWT fallback. Device hashing redesign needs a separate compatibility/migration plan.

Updated the platform test's short synthetic Settings key. No platform recovery/MFA bypass was introduced. Tests use only the clean environments described above:

- `python -m unittest test_phase11_jwt_configuration test_final_jwt_dependency_guards test_entitlement_key_rotation -v`: **15 passed** after final configuration changes, including four new configuration tests and the original 11 compatibility tests.
- `python -m unittest test_phase10_platform test_phase9_fiscal test_phase4b_devices -v`: **40 passed, no skips** in the disposable database, after fallback removal and initial settings validation. The final algorithm-specific validation then passed the focused 15-test suite. Platform tests include synthetic recovery; their printed recovery message refers only to the private cluster. No installed platform state changed.
- `git diff --check`: passed.

Retained logs: `artifacts/phase11-security-20261118/`. Before a future release, operators must separately verify the installed secret meets the new requirements without exposing it. A failing production preflight is a release blocker, never authorization to rotate keys or deploy. This increment does not implement revocable business sessions/reset/remember me or handoff.
