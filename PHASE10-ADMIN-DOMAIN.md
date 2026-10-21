# Phase 10 — admin.apexpos.cloud configuration proposal

Status: **prepared and locally verified, NOT deployed**. Continued from
`247b285b0151794026c20d71b1ea50aa610ad6b4` on `phase10/platform-management`.
No live files, service settings, database records, certificates, DNS, APKs or
firewall rules were changed. No production login or financial action was run.

## Read-only findings — 21 October 2026 UTC

| Check | Finding |
| --- | --- |
| Admin DNS A | `187.77.179.100`, TTL 14400; also confirmed against authoritative `helios.dns-parking.com` |
| Admin AAAA / CNAME | No records returned; no IPv6 listener/address is assumed |
| CAA at admin and apex | No records returned; no observed CAA restriction requiring adjustment |
| DNS provider | `helios.dns-parking.com`, `aster.dns-parking.com` |
| Admin HTTPS | **Blocked:** curl error 60, certificate hostname mismatch; verification was not bypassed |
| Existing API certificate | SANs api/pos/backoffice.apexpos.cloud only; valid 30 Sep–29 Dec 2026, does **not** cover admin |
| Active POS root | `/var/www/apexretail-pos` |
| Active Backoffice root | `/var/www/apexpos-backoffice` |
| Active API upstream | `http://127.0.0.1:8000` |
| Active Nginx files | `/etc/nginx/sites-enabled/apexretail.conf`, symlinked `apexretail-backoffice.conf`; neither contains the admin server name |
| API health | `GET https://api.apexpos.cloud/api/health`: `{"ok":true,"app":"ApexRetail POS"}` |
| POS / Backoffice | Both HTTPS index requests returned 200 with valid TLS verification |
| API service | `apexpos.service`: active/running; reported working directory `/root/apexretail-pos/backend` |
| Phase 10 deployment | Public OpenAPI currently contains **no `/api/platform/` paths**; existing Phase 10 source is not assumed deployed |

No manual DNS change is currently needed. Keep A `admin → 187.77.179.100`.
Do not add AAAA without verified VPS IPv6 routing/listeners. Recheck DNS/CAA at
approval time; record changes after this review may affect issuance.

## Existing application integration

There is still one Backoffice application and the original Platform Admin
Console. `platformEntry.ts` selects that console automatically on the **exact**
admin hostname (including normal DNS case/trailing-dot equivalence). The prior
`?console=platform` entry remains compatible. Other hosts retain their tenant
entry and API behavior. Hostname selection is **not** an authorization boundary.

On admin, the existing dedicated platform Axios client now uses `/api`, so calls
are same-origin `/api/platform/...`. It does not inherit the business token
interceptor. This avoids adding a new backend CORS origin. Existing backend
opaque-session checks, mandatory MFA, role permissions and audit logging remain
unchanged; tenant owner/employee JWTs cannot authorize platform functions.

Browsers isolate storage by origin. First access on the new domain requires
platform sign-in and MFA; do not copy old browser tokens, clear tenant storage,
or migrate business credentials. POS queues and employee sessions are untouched.

## Proposed hosting and TLS

Two **uninstalled** templates:

- `ops/nginx/admin.apexpos.cloud-acme.conf.example`: HTTP-only bootstrap, serves
  ACME challenge files, returns 503 elsewhere. Never enables the console alone.
- `ops/nginx/admin.apexpos.cloud.conf.example`: dedicated HTTP/HTTPS vhost,
  existing Backoffice document root, dedicated admin certificate, platform-only
  API proxy to the existing backend. All unrelated `/api/` routes return 404.

No existing vhost is replaced. There is no second backend, database, admin
application or staging environment. The admin host serves the same reviewed
Backoffice build as the existing Backoffice root after separately approved
release publication. Static assets use root base `/`, not `/backoffice/`.
Downloads remain in their existing POS/API locations; this host does not publish
APKs, project directories, dotfiles, private keys, dumps or source maps.

The proxy retains `/api/platform/` URIs by using `proxy_pass` **without** a URI
suffix, as documented by [Nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass).
Authorization forwarding is explicit; API caching and automatic upstream retry
are disabled. The dedicated host disables access logs and platform proxy error
logging of request URLs, and sends no-store/referrer/frame/content-type headers.
Application audit logs remain enabled. Proposed TLS is 1.2/1.3; check negotiated
protocols after deployment because shared/default Nginx TLS behavior must also be
considered. This work does not change the broader server TLS policy.

Use a **new dedicated** Let's Encrypt certificate named `admin.apexpos.cloud`,
not an expansion/replacement of the shared API certificate. Use Certbot's
[webroot certonly workflow](https://eff-certbot.readthedocs.io/en/stable/using.html?highlight=cron)
to avoid an installer rewriting other vhosts. Certbot is installed, but no
issuance, renewal, account change or challenge was performed in this task.

## Approval-gated production procedure — NOT executed

1. Obtain explicit approval for the final source/build, full Phase 10 backend and
   pending migration release **and** this new Nginx/TLS host. Domain approval alone
   is not approval to deploy Phases 7–10. Recheck live revision and source,
   deployment lock, fresh backup/restore readiness, existing host configuration,
   ports, DNS and current public availability. Stop on any mismatch.
2. Follow the existing reviewed release/backup/migration procedure. The verified
   MFA-aware Phase 10 backend, `p10a_platform_management` and provisioned protected
   `PLATFORM_MFA_KEY` are prerequisites. Rehearse the full pending migration chain
   against a fresh isolated restore before authorizing production migrations.
   Preserve all current tenant records, keys and configuration. Do not start an
   incompatible old backend against a newer schema. Existing Phase 10 evidence
   does not substitute for this production-specific gate.
3. Stage and verify the matching **existing** Backoffice build with
   `VITE_API_BASE_URL=https://api.apexpos.cloud/api npm run build -- --base=/`.
   Keep a full existing-asset backup and hashes outside the live root, preserve
   existing unrelated/download files, and use the reviewed publisher with assets
   first/index last. Never publish localhost/test-key verification artifacts.
   POS need not be republished for this domain change. Stop unless backend routes
   are available, MFA works, and source/build hashes match the approved candidate.
4. Back up the active Nginx configuration/metadata and verify no duplicate admin
   `server_name` exists. Preserve root ownership and existing protected-file
   permissions. Under approval, prepare an ACME-only webroot
   `/var/www/apexretail-acme` with no project/configuration files and enable only
   the proposed bootstrap as a **new** `apexretail-admin.conf` vhost. First run
   `nginx -t`; on failure do not reload. If successful, gracefully reload and
   recheck POS, Backoffice and API. Do not stop/restart application services for
   a vhost-only change.
5. After externally verifying the challenge route, the approved operator runs:

   ```sh
   certbot certonly --webroot -w /var/www/apexretail-acme --cert-name admin.apexpos.cloud -d admin.apexpos.cloud
   ```

   Use the authorized existing CA account/contact and explicit terms approval;
   no invented email or automatic acceptance. Verify the resulting leaf SAN,
   trust chain, dates and private-key permissions. Do not publish test/self-signed
   certificates or use `curl -k`. If issuance fails, leave the console unavailable
   and investigate; do not substitute another hostname's certificate.
6. Replace **only** the new bootstrap vhost with the reviewed final template.
   Confirm the actual Backoffice root still matches the proposal, certificate
   files exist, upstream is the approved Phase 10 backend and platform paths are
   preserved. Run live `nginx -t` and review warnings/conflicts before a graceful
   reload. Preserve all existing POS/API/Backoffice/download routes.
7. Verify externally, including Chrome on the owner's Android:
   - `https://admin.apexpos.cloud/` has a trusted hostname-matching certificate
     and loads the existing platform sign-in (no query string required).
   - HTTP redirects to the correct HTTPS host; ACME renewal path still works.
   - MFA is mandatory; business-owner/employee tokens receive 401; support/billing
     roles cannot perform root-only operations. Do not probe real passwords or
     create production financial records during health checks.
   - Authenticated owner verifies dashboard/navigation, businesses, subscriptions,
     devices, settings and sanitized fiscal pages using read-only actions.
   - `/api/sales`, private-file paths and unconfigured tenant APIs on this host
     return 404. No new cross-origin dependency or credential caching appears.
   - Existing POS/Backoffice/API remain healthy and retain approved asset hashes.
     Check production record/financial baselines using the release runbook.
8. Review the existing Certbot renewal scheduler. Test only the dedicated lineage
   when authorized (`certbot renew --cert-name admin.apexpos.cloud --dry-run`),
   and configure a reviewed renewal deploy hook that performs `nginx -t` before
   graceful reload. Do not alter unrelated renewal configurations. Keep private
   keys/CA state out of the repository. No unattended renewal readiness is claimed
   until the real lineage and hook are verified.

## Rollback plan

If Nginx validation fails, **do not reload**. If a new-host change affects existing
sites, restore/move aside only the new admin vhost, revalidate and gracefully
reload the previously backed-up configuration; verify the original three hosts.
Do not remove/revoke existing certificates, stop the API or edit live data.
If matching Backoffice publication fails, use its verified asset snapshot and
existing controlled rollback publisher, assets first/index last, then leave the
admin host disabled until a compatible candidate is approved. Preserve downloads
and browser storage. A domain rollback does **not** downgrade schemas, restore an
older database or roll back backend releases; those require separate reviewed
forward-recovery/compatibility decisions. Preserve migration/MFA data and audit
evidence. Never blindly restore a database over newer business transactions.

## Verification and limitations

- 25 POS/Backoffice regression, lint and build commands passed, including three
  exact-host/API-selection unit tests. Existing warnings remain: POS 2,
  Backoffice 8 and bundle-size advisories; no new lint errors.
- 42 backend platform/billing tests + 18 subtests passed against existing isolated
  databases, with three existing deprecation warnings. Covers MFA, tenant-token
  rejection, role boundaries, sessions, subscriptions and audited management.
  Backend source/contracts were not changed for the domain.
- 9 actual-entry browser checks passed using intercepted synthetic responses and
  loopback assets: host selection, same-origin requests, no business-token leak,
  MFA gating, support permissions, 390px layout, storage preservation and forged
  session rejection. No production/external browser traffic.
- Proposed vhosts passed **isolated** Nginx syntax validation. Four loopback TLS
  test cases passed with synthetic static files/upstream: redirect/ACME, SPA,
  unchanged API URI/auth forwarding, blocked tenant/private paths. The temporary
  test certificate/process/files were disposed; live Nginx was not signaled.
- Existing **16-check** console/navigation browser suite passed again; final
  results are in the evidence directory. Original full backend run (485 tests +
  187 subtests) is retained in the prior Phase 10 evidence, not misrepresented as
  rerun here.

Evidence: `/root/apexretail-pos/artifacts/phase10-domain-20261021/`.
Live configuration hashes before/after checks were identical. Real certificate
issuance, live combined `nginx -t`, renewal, public admin login/MFA and physical
Android acceptance remain **PENDING**, awaiting explicit production approval.
No assertion of current live platform accessibility is made.
