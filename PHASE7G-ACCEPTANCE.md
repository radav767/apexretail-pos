# Phase 7G — Android acceptance and mandatory shifts

Baseline: verified Phase 7F `79053396d78a50f24950bd6065a81b772504b5cc`.
Development branch: `phase7g/android-shift-acceptance`, isolated worktree `/tmp/apexpos-phase7f`.
No production deployments, backend/schema changes, production database access, data resets, APK installation or queue deletion.

## APK verification and why a new acceptance build was necessary

The retained Phase 7F APK remains byte-for-byte unchanged:

- `/root/apexretail-pos/artifacts/phase7f-acceptance-20261020/apexretail-phase7f-acceptance-build6.apk`
- SHA-256 `0e437d4b7fe21949c6046a5e93888501526bbfb0ff07bc171069d41fd3e05e0a`.
- Its v1/v2 signature verifies against the existing certificate SHA-256 `bb0d2ca7de6baa73009a4694fd1de1946548dc432992ba6443943c54306deb74`.

That APK lacked the new pre-submit/offline active-shift guard, and its staging public keyring omitted lifetime-policy fields required by the verifier. These software findings required a new **staging-only** build; integrity/signature verification alone does not make the old APK suitable for the final offline acceptance tests. Keep it as historical evidence, not the recommended Phase 7G acceptance build.

New acceptance identity:

- Package **`cloud.apexpos.pos.staging`**, launcher **ApexRetail STAGING**.
- Version code **7**, version name **`1.4.0-phase7g-acceptance`**.
- Production package `cloud.apexpos.pos`, default version code 6 and release signing configuration are unchanged.
- Same existing signer, no new Android signing key. Once the final artifact checks pass, this can update the Phase 7F **staging** package without uninstalling it. It deliberately cannot replace the differently named production app.
- Compiled API is **`https://localhost:18770/api`**, not the production API. Local staging CA is scoped to localhost/127.0.0.1 in the acceptance overlay. The final APK checksum, source commit and asset list are recorded in the accompanying manifest.

## Implemented corrections (development/staging only)

1. Online submission and new offline queue creation now check active-shift company, branch, cashier and register identity when enforcement is required. Offline creation additionally requires the original shift token. Existing queued transactions are not rewritten, deleted or reassigned; server signature, timestamp, idempotency and closed-shift quarantine validation is unchanged.
2. The acceptance build sets `VITE_REQUIRE_CASHIER_SHIFT=true`; normal builds keep their existing per-business configurable policy. A new synthetic Phase 7G business has backend `shift_enforcement_enabled=true` and no cutoff. Existing production settings and Phase 7F businesses were not changed.
3. A cashier without a matching active shift sees **Start Shift**; Return to Sales cannot dismiss a mandatory prompt. Blank/whitespace opening cash defaults to zero. Nonzero cash remains supported. Shift mutations remain online-only.
4. The direct Shift Management destination now forwards `onShiftChanged` to Sales. Closure clears the active shift cache rather than leaving Sales with a stale open shift. Checkout panels are hidden while another operational page is selected, without destroying the cart or its state.
5. The staging public keyring now includes explicit trusted lifetime limits (43,200 seconds snapshot; 259,200 seconds offline grace), using the existing staging key unchanged. The build refuses missing/nonpositive/noninteger limits. Authentication/signature/token/PIN/device validation was not bypassed or relaxed.

## Automated results

| Check | Result |
|---|---|
| New real HTTPS shift scenarios | **29 passed**, new synthetic tenants only |
| New mandatory-shift browser scenarios | **22 passed**, no page errors or external requests |
| Shift identity policy | **16 executable assertions** passed |
| POS/Backoffice regression, lint, build commands | **24 passed** after final UI/keyring fixes |
| Focused backend shifts, Z Reports, permissions | **30 tests + 50 subtests passed**, 5 deprecation warnings |
| Staging isolation guards | **3 unittest methods passed**, including production-target rejection |
| Android lint/unit/assembly, signer/assets | Final logs and APK verification accompany this report |

The prior Phase 7F full backend suite (374 tests + 126 subtests) is retained as baseline evidence; backend source and migrations are unchanged, so it was not needlessly repeated. The focused suite above was rerun. Tests use the separate staging cluster or existing synthetic regression databases, never the production business database.

The first repeated-close assertion compared raw decimal string scale. It was corrected to compare every response field with decimal representations normalized; financial totals, identity, status and closing timestamps remain identical. Earlier synthetic fixtures were retained, not reset. A case-sensitive test selector was also corrected to the actual uppercase report button.

## Shift acceptance results

| Required action | Verification |
|---|---|
| PIN login, open Sales, Start Shift | Real browser PIN authentication and mandatory prompt passed |
| Opening cash optional/zero | API omits balances; UI clears amount; both default to zero |
| Nonzero opening | Cashier B opens with 25.00 after A closes |
| Independent cashier shifts | B sees no A shift; ownership and distinct IDs verified |
| Cannot sell without shift | Server HTTP 409; checkout blocked in browser; client pre-submit guard |
| No overlapping drawer ownership | B opening while A owns register returns HTTP 409 |
| Own closure only | B cannot close A shift (HTTP 403); authorized own closure succeeds |
| Closing report | Immutable JSON, PDF, 58 mm and 80 mm HTML; actual browser report modal |
| Cash variance | A expected 10, counted 9, shortage -1; B opening 25/count 27, overage +2 |
| Permissions | Restricted employee gets HTTP 403 for open, close and report access |
| Retry protection | Duplicate open/close and sale retries preserve identity and totals; stock deducted once |
| Closed-shift protection | New sale rejected; Sales returns to Start Shift; original queues retained |
| Offline/reconnection | No shift can be opened offline; checkout remains blocked without one; cached authorization verifies after reconnect |

Offline sale synchronization/quarantine backend logic was not changed. Phase 7F regression evidence remains applicable; physical Android offline payment, process-kill recovery and synchronization are still pending, not claimed as hardware-tested.

## Safe download and installation instructions — not executed

Final APK is preserved outside `/tmp` under:
`/root/apexretail-pos/artifacts/phase7g-acceptance-20261020/apexretail-phase7g-acceptance-build7.apk`.

No public HTTPS download route was created. There is no approved separate HTTPS staging host, and production Nginx/download directories must not be changed for this task. A local artifact link is not a public Android browser URL.

Safe available method:

1. From a trusted computer, use the already authorized administrative SSH account to copy the protected APK over SSH. Replace placeholders with your existing approved server/account; do not weaken directory permissions:

   ```sh
   scp <authorized-admin>@<approved-server>:/root/apexretail-pos/artifacts/phase7g-acceptance-20261020/apexretail-phase7g-acceptance-build7.apk .
   sha256sum apexretail-phase7g-acceptance-build7.apk
   ```

2. Match SHA-256 with `release-manifest.json` supplied with the APK.
3. Connect the Android test phone by USB using File Transfer/MTP and copy the APK into Downloads. This transfers a file only; it does not install, uninstall, clear storage or change either app.
4. After owner approval for installation, open the file using the phone's Files app. Verify **ApexRetail STAGING**, package `.staging`, version code 7. If Phase 7F staging is already installed, accept its signed update; never uninstall the production app or clear either app's data.
5. Optional computer-assisted staging update, only after approval: `adb install -r apexretail-phase7g-acceptance-build7.apk`. Never use `adb uninstall`, `pm clear` or downgrade flags.

If phone-browser-only download is required, provide/approve a **separate HTTPS staging host** or an approved private file-transfer service. Do not expose runtime configuration, backups, synthetic credentials or private signing/TLS keys. Do not disable certificate checks or create a public production-directory APK link.

## Connecting the acceptance app

The app intentionally cannot contact production. For this loopback staging setup:

1. Computer: `ssh -L 18770:127.0.0.1:18770 <authorized-admin>@<approved-server>`.
2. With authorized USB debugging on the test phone: `adb reverse tcp:18770 tcp:18770`.
3. Open **ApexRetail STAGING**, not the production app. Use the completed synthetic Phase 7G fixture's credentials, retrieved over the approved administrative channel from the protected `phase7g-current.json` pointer under `/tmp/apexretail-phase7f-runtime`. Credentials are not embedded in the APK or report.
4. Keep SSH/ADB forwarding running. Use Android **7/API 24 or newer** for the acceptance overlay's custom CA; API 23 support with this local CA remains unverified/unsupported. The production minimum was not changed. The local TLS certificate expires 30 days after Phase 7F preparation.
5. A phone without this tunnel arrangement needs an approved separate staging endpoint and a reviewed API/CA acceptance build. Never point this APK at production as a workaround.

## Physical/manual acceptance checklist — all PENDING

Use synthetic staging data only, record device model/Android/WebView versions, tester, timestamp, expected/actual outcome and evidence. Do not sign off a failed or unexecuted case.

| Area | Cases to execute on actual hardware |
|---|---|
| Installation/storage | Verify `.staging` version 7/signer; separate production launcher/data; stage-to-stage upgrade retains its session/device/printer settings and pending synthetic queue |
| Login | Email/password once, device registration, valid/invalid PIN, cashier switch, restart, revoked/disabled employee rejection |
| Mandatory shifts | PIN → Sales → Start Shift; blank and nonzero float; no bypass; A/B drawer isolation/handover; own closure; shortage/overage; permission denial |
| Sales | Cash/card/mobile; totals/stock/history; ambiguous timeout checked before retry; duplicate retry uses original identity |
| Products | Search/barcode/camera permission, categories, variants, component products and price levels under appropriate roles |
| Inventory/reports | Branch restrictions; one stock movement per sale; POS/Backoffice consistency; existing reports and Z Report PDF viewing/reprint |
| Offline | Warm verified authorization, active signed shift, airplane mode sale, forced process stop/restart, reconnect and sync once; test expired/revoked credentials and stale closed-shift quarantine without deleting queues |
| Bluetooth | Real paired 58/80 mm printers; Android 12+ grant/deny; reconnect, power/paper failure; receipt once after sale |
| USB | OTG grant/deny, unplug/replug, receiver handling, receipt output and error recovery |
| Network | Actual LAN printer route/port, paper-out and ambiguous-write recovery; no automatic duplicate printing |
| Kitchen/bar | Two stations, product/category routing, prepayment KOT, item changes, queue retries and authorized reprints; no duplicate sale/payment/stock/order |
| Chrome/native differences | Browser/system printing versus native Bluetooth/USB/TCP bridge; do not assume raw printer access exists in Chrome |

No physical phone or printer was used. Android build success, browser emulation and generated thermal HTML are not physical acceptance.

## Warnings and readiness

- Native lint: zero errors expected from final run; 18 existing warnings include locale handling, manifest/resource advisories and API 23's lack of custom network-security configuration support. The single native example unit test is not hardware coverage.
- Frontend hook/Fast Refresh and >500 kB chunk advisories remain nonfatal. Focused backend has five dependency deprecation warnings, no test skips/failures.
- The established signer is the existing Android Debug certificate; no replacement was generated. Signing-key hardening is a separate reviewed release concern.
- Exact final source commit, APK signature/hash and byte-for-byte embedded build verification are in the packaged manifest; originals remain preserved.
- No Phase 7G database migration is required. Current staging revision remains `p7j_variant_batches`; production revision/configuration was not queried or changed in this task.
- **Production readiness: PENDING / NO-GO for deployment.** Required physical Android/printing/offline acceptance, direct phone connectivity if needed, and a separately authorized production migration/backup/recovery/security review remain outstanding. No deployment or automatic APK installation is authorized by this report.
