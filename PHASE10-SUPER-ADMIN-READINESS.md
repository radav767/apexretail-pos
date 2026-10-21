# Phase 10 — final Super Admin authentication and HTTPS preparation

21 October 2026 UTC. Continues preparation commit
`d4b2eccb36a265f6a234954da25a530530a2056c`.
Rehearsed runtime remains **932557e3abca1a2fa046b2d04d0d6f8c6d4bcc35**; no runtime
application, frontend source or migration change was needed. No deployment approval
is implied. Consolidated order: `PHASE7-10-CONSOLIDATED-DEPLOYMENT-PLAN.md`.

## Decision

**Authentication/MFA software verification: PASS. Live Super Admin: NO-GO.**
Actual MFA provisioning/enrollment, dedicated HTTPS and pending backup custody/
off-server recovery approvals are not complete. The domain must not be activated
or credentials entered through the current certificate mismatch.

## Verified implementation

Reused Phase8 `platform_auth`, `platform_router`, commercial billing and Phase10
`platform_mfa`/`platform_management`. It is the existing Backoffice platform entry,
not another application. Backend access is enforced independently of the hostname
or browser role. The admin hostname uses same-origin `/api/platform/`; no global
CORS relaxation or business-token forwarding is required.

| Feature | Actual verification | Result |
|---|---|---|
| Password authentication | Isolated real HTTP/DB login; no session before second factor | PASS |
| MFA enrollment/verification | Encrypted TOTP secret, RFC vectors, ASCII codes, challenge expiry, replay/lockout | PASS |
| Wrong/missing MFA key | Fails closed503; restoring original synthetic key permits verification without tenant changes | PASS |
| Provisioning mechanism | Private owned parent/file, exclusive/no-follow creation, no overwrite or value output | PASS on temporary fixtures only |
| Permissions | Root/billing/support restrictions; current role rechecked; business JWT denied platform routes | PASS |
| Sessions | Hashed opaque credentials,30-minute expiry, logout/revocation/disabled-account rejection | PASS |
| Session directory | Non-root only sees own sessions; no token hash serialization | PASS |
| Audits | Login/MFA/logout/management/recovery events; no password/token/factor payloads | PASS |
| Audit protection | Runtime role SELECT/INSERT only; UPDATE/DELETE denied; existing immutable triggers | PASS on isolated PostgreSQL |
| Tenant/billing isolation | Business owner can read own billing, not another company; no platform access | PASS |
| Subscriptions | Existing activation/renewal/limits/billing/idempotency/immutability regressions | PASS |
| Browser storage | Platform sessionStorage separate from business localStorage; logout preserves business storage | PASS with synthetic responses |
| Phone/navigation | Dedicated host routing, MFA gate, support restrictions and responsive screens | PASS with synthetic responses |

`super_admin` manages platform settings/admins and authorized commercial/device
operations. `billing` has billing actions/read summaries, not root management.
`support` is read-only except own-session controls. Platform administrators have
authorized cross-business platform summaries, not customer-password access or
tenant impersonation. Ordinary company owners/employees never become platform
administrators via their existing login/PIN.

## MFA commissioning — prepared, not performed

Use existing `ops/phase10/mfa_provision.py` and proposed systemd EnvironmentFile
drop-in. The production file `/etc/apexretail/platform-mfa.env` is absent; no real
MFA key, administrator password/account or factor was created. UTC clock is NTP
synchronized, suitable for the required real authenticator acceptance.

After explicit approval and backup/secret-custody acceptance:

1. Owner selects the initial administrator identity and separate authorized
   recovery custodian. Establish encrypted MFA-key escrow/recovery first.
2. Authorized root provisions one independent Fernet key directly into a new0600
   file in root0700 `/etc/apexretail`. Existing provisioning refuses overwrite;
   validate without printing its value. Never rotate JWT/entitlement keys or copy
   secrets into Git/chat/logs. Verify an approved recovery copy privately.
3. Integrate the reviewed EnvironmentFile without replacing existing DB, signing,
   entitlement or service overrides; restart only during the approved release.
4. After schema/backend/HTTPS readiness, use existing local bootstrap CLI with
   getpass, not command-line passwords/default credentials. At least12 characters
   and at most72 UTF-8 bytes; duplicate accounts refused and bootstrap audited.
5. Owner privately enrolls the authenticator through valid HTTPS. Do not record
   setup keys, codes or authenticated screenshots. Confirm second-factor login,
   logout, session expiry/revocation and role boundaries.
6. Verify recovery using existing operator-only recovery procedure: authorized
   identity review and current platform password, revoke sessions/challenges,
   mandatory new enrollment, complete audit. No password-only access fallback.

Real custodian/device enrollment and recovery remain manual acceptance gates.

## HTTPS/Nginx status and proposal

- DNS A resolves to **187.77.179.100**. No AAAA answer and no explicit CAA answer
  at the admin hostname or apex were observed; no DNS change made.
- **Live HTTPS fails curl60**: current certificate covers api/backoffice/pos,
  not admin.apexpos.cloud; that shared certificate expires29 December2026.
  Dedicated admin certificate/key files are absent. Do not bypass validation.
- Active Nginx has no admin vhost. Verified POS root `/var/www/apexretail-pos`;
  Backoffice root `/var/www/apexpos-backoffice`. Live `nginx -t` PASS; hashes of
  existing main/POS/Backoffice configuration unchanged.
- Existing ACME/bootstrap and final admin templates remain uninstalled. Final
  proxy forwards only `/api/platform/`, preserves Authorization and URI, disables
  cache/token URL logging and blocks tenant APIs/sensitive files. No global route
  replacement, API change or additional application is proposed.
- Hardened the **proposal only** to block `/downloads` on the admin hostname:
  shared Backoffice downloads/previews must not become admin-host file routes.
  Existing POS/Backoffice downloads and APKs are untouched. Private Nginx test
  now verifies rejection even when a synthetic preview actually exists on disk.
- Prepared `ops/letsencrypt/admin-renewal-hook.sh.example`. It skips other lineages,
  validates Nginx first and only then gracefully reloads for the dedicated admin
  certificate. Three tests use temporary fake commands: no real reload.
- Certbot is installed; its existing timer is active. Directory hooks are empty
  and no global cli.ini hook directive was found. No Certbot request/dry-run,
  issuance, renewal-profile change, hook installation or Nginx reload occurred.

Approval needs: owner ACME contact/terms, narrowly scoped HTTP challenge bootstrap,
dedicated certonly/webroot issuance (not auto-rewriting existing Nginx sites),
chain/hostname/expiry/key-match checks without key output, final vhost and guarded
renewal hook, renewal acceptance/failure alerts. Preserve existing certificates.
Only final valid HTTPS plus ready backend/MFA permits admin enrollment.

## Final verification

- **54 tests +33 subtests passed**, zero failures/errors/skips;3 existing Pydantic
  deprecation warnings. Existing rollback-only databases; no database created,
  reset, migrated or restored in this task.
- **16 console browser checks +9 domain-entry browser checks passed**. Actual
  components, intercepted synthetic responses, no production/external requests.
- **4 private Nginx tests passed**, with temporary self-signed test certificate
  and synthetic upstream. Not a claim of real public HTTPS acceptance.
- Live POS200, Backoffice200, API `ok:true`. API/watchdog/backup timers active;
  current Nginx valid/unchanged, no restart or live configuration edit.
- Production **apexretail_pos**, revision **p5h_runtime_write_permissions**.
  Read-only comparison: original hashes, financial controls and owner/ACLs match
  the verified backup; five open shifts intact; shift enforcement OFF.
- Pending backup activation record still absent. Previous encryption preparation
  is not real custody/off-server acceptance; no backup gate was bypassed or rerun.

## Remaining owner approvals

1. Complete prior backup recipient/escrow/off-server/real recovery/monitoring gates
   and approve activation separately. Current job remains plaintext/preserve-all.
2. Approve initial platform administrator identity, MFA key escrow/provisioning,
   service drop-in and supervised real authenticator/recovery acceptance.
3. Approve ACME bootstrap/issuance, dedicated certificate/renewal, final admin
   vhost and validated graceful reload. No existing host routes may be replaced.
4. Approve exact production-built backend/POS/Backoffice artifacts, maintenance,
   the full14-revision migration chain and controlled release per consolidated plan.
5. Sign off the relevant Phase7 physical Android/printer workflows and Phase8
   commercial onboarding policies. Phase9 live fiscalisation remains a separate
   **NO-GO**: connector/onboarding/specification/certification work is outstanding.

No live credentials used, artificial production transactions, APK build,
production business/schema changes, database creation or deployment occurred.
Private evidence: `/root/apexretail-pos/artifacts/phase10-super-admin-readiness-20261021/`.
