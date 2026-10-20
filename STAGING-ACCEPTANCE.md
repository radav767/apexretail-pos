# Phase 7F — isolated acceptance environment

## Status and scope

Baseline: `390065557b1940e35c528fb407c51b3a3018af31` (verified Phase 7E).
Integration branch: `phase7f/staging-acceptance`; worktree `/tmp/apexpos-phase7f`.
No production deployment, migrations, business writes, service restarts, APK installation or queue deletion was performed.
Production readiness is **PENDING**, not GO: physical Android/printer acceptance and an approved remotely accessible staging route remain outstanding.

## Configuration inspected

| Component | Existing production | Acceptance environment |
|---|---|---|
| API | `apexpos.service`, loopback `8000`; immutable backend `340faad2802246d8f29ab3c0f3de9352612f7136` | dedicated `apexstage7f` OS account, loopback `18771` |
| POS | Nginx `pos.apexpos.cloud`, `/var/www/apexretail-pos` | `https://localhost:18770/` |
| Backoffice | Nginx `backoffice.apexpos.cloud`, `/var/www/apexpos-backoffice` | `https://localhost:18770/backoffice/` |
| Database | existing `apexretail_pos`, not connected or changed by this work | **separate PostgreSQL 14 cluster**, Unix socket only, port identity `55437`; `apexretail_phase7f_acceptance` |
| Android | `cloud.apexpos.pos`, version 6 / 1.4.0; existing established signer | **`cloud.apexpos.pos.staging`**, version 6 / `1.4.0-phase7f-acceptance`, label **ApexRetail STAGING** |

Production POS and Backoffice returned HTTP 200; `/api/health` returned `ok: true` during this review. This is a read-only availability check, not a production transaction or financial reconciliation test.

## Isolation and credentials

- Runtime `/tmp/apexretail-phase7f-runtime` is mode 0700, owned by the locked, nologin staging account. Private runtime configuration/keys are 0600.
- Database has no TCP listener. Neither application nor migration connection uses the production cluster/socket. Runtime validation rejects any other database, socket, port, user, driver, environment or source directory, including under optimized Python.
- Staging has separate JWT, entitlement and TLS keys; no production environment, credentials, entitlement keyring, sales, inventory or queues were copied.
- Staging account cannot read the production backend environment file. Frontend CSP restricts connections to the staging origin; browser acceptance also aborts external requests. APK assets contain the staging API and staging entitlement public key, not the production API URL.
- The fresh cluster needs the explicit staging-only application DML baseline in `staging/grant_stage_runtime.sql`. Phase 7 column-specific and append-only grants remain intact. The script refuses any other database/cluster identity. This is **not evidence of production ACL parity**; production permissions require a separate release review.
- Synthetic credentials and API test recovery state are in protected `acceptance-accounts.json` under the runtime directory, never in web assets, screenshots, Git or public output. Operator retrieval must use the approved secure server channel.
- No public staging hostname or Nginx change is configured. Do not point these builds at production or enter production credentials.

## Reproduction and operation

Preparation scripts intentionally pin this isolated worktree/runtime and never reset an existing database:

1. Review the source commit and existing caches/environment.
2. Approved root execution: `/tmp/apexretail-phase7b-venv/bin/python staging/prepare_phase7f.py`. Existing runtimes are refused; `--resume-migrations` only resumes the same guarded staging instance.
3. Copy **public** keyring and public local CA into the ignored acceptance build inputs. Never copy a private key into Android or web sources.
4. Build POS using `VITE_API_BASE_URL=https://localhost:18770/api`, `VITE_BACKOFFICE_URL=https://localhost:18770/backoffice/`, and `ENTITLEMENT_PUBLIC_KEYRING_FILE` pointing to the staging public keyring. Build Backoffice using the same staging API base.
5. Run `staging/start_phase7f.py` as approved root. It refuses occupied ports/existing asset publication. `--refresh-backoffice` updates only the fixed staging Backoffice directory, publishing index last; it never targets production document roots.
6. Verify `/api/staging-identity` over TLS against the staging CA before creating any fixtures. Expected database `apexretail_phase7f_acceptance`, runtime role `apex_user`, revision `p7j_variant_batches`.
7. Run `staging/acceptance_api.py` as `apexstage7f`. It uses real registration/authentication and synthetic transactions, preserving its test references for idempotent retry. It must stop on unexpected status codes. If another acceptance session is active, coordinate logout rather than bypassing the session checks.
8. Run `staging/acceptance_browser.mjs` with Playwright/Chromium installed at the documented local cache paths. POS and Backoffice use independent browser storage profiles. Browser TLS bypass is limited to this automated loopback self-signed test context; Android does **not** disable TLS validation.
9. Native build: synchronize staging POS assets with Capacitor; use JDK 21, `/opt/android-sdk`, cached Gradle 8.11.1; run `--offline --no-daemon lintAcceptance testAcceptanceUnitTest assembleAcceptance`. Never build/publish the production APK in this phase.
10. Run `staging/verify_apk.py`. Compare package, signer and every embedded web file with the final tested build. Preserve APK, evidence and public certificate in the protected persistent acceptance artifact directory.

The local TLS certificate expires after 30 days. Existing preparation must not be rerun to overwrite its database or keys. Reviewed certificate renewal plus a new acceptance APK would be needed after expiry.

## Verified results

- Backend: **374 passed, 126 subtests passed, 0 failed, 0 skipped; 6 deprecation warnings**. Existing synthetic regression databases only; no production database targeted.
- Frontend: **24 script-level checks** (POS/Backoffice regression suites, lint and production-mode builds). Final reports are packaged separately. Hook/Fast Refresh advisories and the Backoffice >500 kB chunk warning remain non-fatal.
- Staging isolation: **3 unittest methods**, including five rejected connection variants.
- Real HTTPS API: **18 checks**: two companies, password/PIN/device auth, shared products, online cash sale/retry, signed offline sale synchronization/retry, exactly-once stock deduction, Backoffice history/valuation, shift reconciliation, PDF and 58/80 mm HTML generation, restricted cashier and cross-company/branch denial.
- Real browser: **78 checks**, no page errors, API errors or external requests. Owner navigation/feature destinations, settings, browser Back, dashboard buttons and logout; actual authenticated screenshots at 1440/820/390/320 pixels. These are navigation/read checks, not exhaustive CRUD or every role/action permutation.
- Android: `lintAcceptance`, `testAcceptanceUnitTest`, `assembleAcceptance` pass. Lint: **0 errors, 18 warnings**. Native unit suite contains **one example smoke test**; it is not a printer/device test. APK v1/v2 signatures verify and certificate matches the previous APK's public certificate fingerprint. Signer is the existing established Android Debug certificate; it was not generated/replaced here. Review signing-key hardening separately before a future public release.
- Fresh staging migration: complete empty-database chain through `p7j_variant_batches` passed. No new Phase 7F Alembic migration. Phase 7E archived-production-clone upgrade/downgrade/forward evidence remains in the preceding completion report; it was not unnecessarily rerun because backend migrations are unchanged. A fresh live production clone/release permission review is **not** claimed here.
- Fresh custom-format staging backup: archive validation, separate disposable restore, **64 tables** matched by row counts and sorted row-content hashes from the **same exported PostgreSQL snapshot**. Earlier non-snapshot comparison was invalidated by concurrent acceptance writes; no data was deleted/restored over either application database.

## Problems found and corrected

1. Public build keyring was inaccessible inside the private runtime: copied only the public keyring to build inputs; private keys remain protected.
2. Fresh staging cluster lacked legacy runtime DML grants: added a guarded, staging-only baseline. No production ACL or ownership changes.
3. Acceptance TLS lint required explicit subdomain flags: restricted both local hostnames with `includeSubdomains=false`, no warning suppression.
4. Real Backoffice Business Operations navigation exposed a second bundled React instance from shared POS components. `backoffice/vite.config.ts` now deduplicates `react` and `react-dom`; verified with independent Backoffice login/storage and real navigation.
5. Corrected test fixtures/selectors (online versus signed-offline timestamps, required history dates, OPEN SHIFT label, responsive logout control) and snapshot backup comparison. Rejected synthetic requests and original reference state were retained; these were not production or POS queued transactions.

## Android installation and phone connection — operator steps, not executed

This is a **side-by-side acceptance app**, not a production update. Production package and storage remain untouched. Its database, login, printer settings and offline queues are separate; never import production pending queues into it.

1. Obtain the APK from the protected artifact location and verify its SHA-256 against `release-manifest.json`.
2. For a locally connected acceptance phone, create an approved SSH tunnel from the computer to the staging server: `ssh -L 18770:127.0.0.1:18770 <approved-ssh-host>`. Keep it open.
3. With authorized USB debugging on the test phone, run `adb reverse tcp:18770 tcp:18770` on that computer. This only forwards the local staging endpoint; do not run commands targeting the production app.
4. After owner approval for installation, install **only** `cloud.apexpos.pos.staging`, for example `adb install apexretail-phase7f-acceptance-build6.apk`. Do not use uninstall, clear-data, downgrade or production-package replacement commands. Verify the launcher says **ApexRetail STAGING** before entering synthetic credentials.
5. Use **Android 7 / API 24 or newer** for this local-CA acceptance configuration. The underlying production minimum is API 23, but Android 6 does not support the acceptance overlay's per-domain custom CA mechanism; API 23 acceptance remains pending rather than bypassing TLS.
6. Public staging CA is embedded only for exact localhost/127.0.0.1 domains in the acceptance variant. Do not install a global CA or trust-all handler. A phone without the SSH/ADB arrangement needs an approved separate HTTPS staging host; none is published in this phase.
7. Do not regard a successful build/signature check as physical installation, WebView, camera, offline database or hardware compatibility acceptance.

## Acceptance checklist — physical/manual gates remain PENDING

| Area | Automated evidence | Required owner/device acceptance |
|---|---|---|
| Navigation | menu/submenu/feature-grid/Back and mobile width checks pass | actual tablet/phone touch targets, keyboard, accessibility and WebView |
| Authentication | real owner/PIN/device login; permission/isolation regressions | staging APK launch/restart, PIN switching, deactivation/revocation and device reassignment |
| Sales/inventory/reports | synthetic online/offline API idempotency and stock/history/report consistency | cashier completes staged cart/payment; all supported tenders/variants/composites/returns |
| Shifts/Z Reports | opening, cash reconciliation, close, immutable PDF, 58/80 mm HTML | cashier A/B handover, actual counts, physical PDF viewing and thermal pagination |
| Offline | backend/JS retry/recovery suites; signed offline staging synchronization | Android airplane mode, process kill, relaunch, reconnect, duplicate/conflict/quarantine review |
| Bluetooth receipt | bridge permission/queue source regressions, Android lint | paired 58 and 80 mm devices, Android 12+ permission grant/deny, reconnect, power interruption |
| USB receipt | bridge permission/receiver regressions | OTG/USB device permission grant/deny, detach/replug, repeat permission handling |
| Network printer | native network bridge and queue regression coverage | actual reachable LAN printer, address/port, paper-out, timeout and recovery |
| Kitchen/bar | backend KOT routing/idempotency/claim/reprint tests | two physical stations, category/product routing, partial ticket changes and KDS updates |
| Automatic receipt | financial/print separation and retry regressions | physical once-only print after commit; printer failure must not repeat sale/stock/payment |
| Reprinting | backend authorization and queue duplicate/review tests | explicit reprint label, manager approval, ambiguous-write review and audit trail |
| Platform limits | Chrome browser/system print versus Android native bridge inspected | raw Bluetooth/USB/TCP support depends on platform; never claim Chrome has native printer access |
| Financial/legal | regression calculations and separate tips ledger tests | reviewed tip policy, currency/rounding, refund, settlement and payout acceptance |
| Production release | no production mutations; read-only web/API availability | approved migration/ACL rehearsal on fresh production clone, fresh verified backup/recovery and explicit deployment approval |

No Android or printer hardware was connected: ADB device list empty, USB listing only a Linux root hub. All physical print/installation statuses are **PENDING**, never PASS.

The server runtime is temporary and not installed as a boot-persistent service. Keep protected runtime/backups and persistent evidence; no reset/delete script is provided. Request approval before creating public routes, modifying production configuration or deploying any artifact.
