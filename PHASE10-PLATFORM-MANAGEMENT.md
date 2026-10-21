# Phase 10 — existing Platform Admin Console

Development branch: `phase10/platform-management`, based on verified Phase 9
`e81284a089010332dd7667b960c59689b5be3b23`. No production changes, new
application, new staging environment, new database, APK build or deployment.

## Reused implementation and findings

Phase 8 already provided a separate opaque platform session, three administrator
roles, commercial plans, immutable invoices/payment receipts, idempotent manual
payments, renewal history, license suspension/reactivation, capacity checks,
optional-module enforcement, trial/expiry reminders and immutable audit logs.
Those tables and financial flows remain authoritative. The existing Backoffice
entry point remains `?console=platform`; business/employee tokens cannot enter it.

The missing management pages, MFA, session controls, trial defaults and safe
fiscal summaries have been added to this console, not a parallel admin product.

## Delivered actions

| Area | Implementation / verification |
| --- | --- |
| Dashboard | Existing currency-separated billing revenue and subscription counters; added active/suspended business and claimed-device counts, renewal cards and health/fiscal navigation. Counts read real records. Total registered includes archived companies; active means active/nondeleted company minus suspended licenses, not paid subscriptions. |
| Businesses | Search/paginated existing directory; detail/activity counts, plan limits, billing/assignment entry, audited license suspend/reactivate. Existing reactivation rules require a valid paid period. |
| Subscriptions | Existing plan versioning, invoice/payment commands and exact-original retry persistence retained. New optimistic, audited trial extension, exact expiry retry does not extend twice; cannot turn a paid subscription into a free trial. |
| Defaults | Versioned singleton settings: console brand, 1–90 day initial trial duration, suggested billing plan, in-app reminder switch, business-type catalog. Existing trials and existing business profiles never rewritten. Suggested plan does not grant a license without an invoice/payment; catalog does not disable existing types. |
| Devices | Search/paginated device directory, company filter API, sanitized activity, audited revocation reusing existing decommission service and session/assignment-revision behavior. Requires offline-queue/checkout confirmation and refuses open cashier shifts. Never deletes device history. |
| Device activation | Existing active claimed device is an idempotent no-op. Deactivated/unclaimed devices must use existing business-owner registration/claim workflow. Platform cannot resurrect revoked offline authority with a toggle. |
| Fiscal | Read-only company-filtered monitoring: configured/test state, protocol initialization, day state, prepared/document counts, pending operation, error event counts. No keys, credential references, raw payloads, taxpayer secrets, submission button or claim of ZIMRA approval. Counts are preparation/test-protocol evidence, not accepted live receipts. |
| Administrators | Super-admin-only creation and role/availability updates. No password/hash/MFA-secret serializers. Self-demotion/deactivation denied; changes serialized and target sessions revoked. New accounts require MFA enrollment. |
| Sessions | MFA-only 30-minute opaque sessions; own-session list/revocation for billing/support, all-platform sessions for super admin. Never returns session token hashes. |
| MFA | Password followed by 5-minute purpose-limited enrollment/verification challenge, 6-digit/30-second TOTP, ±1 step, persisted replay counter, shared failure budget and 15-minute lockout after five failures. Challenges stored hashed; secrets encrypted. No password-only fallback. Existing password-only platform sessions are rejected, not silently upgraded. |
| Recovery | Audited business owner identity-review request, no account mutation/impersonation/password disclosure. Operator-only platform MFA recovery requires OS/DB authority, current platform password, explicit confirmation and identity-review reference, revokes sessions/challenges, requires fresh enrollment. No public reset backdoor. |
| UI | Existing dark-green theme, dedicated management pages, mobile hamburger, role-specific controls, compact cards, bounded tables, clear error states. Tenant POS design unchanged. |

## Security and external setup

TOTP follows [RFC 6238](https://www.rfc-editor.org/rfc/rfc6238); tests use its
SHA-1 reference vectors. MFA design also considers
[OWASP MFA guidance](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html).
TOTP is not phishing-resistant; no passkey/WebAuthn capability is claimed.

An authorized operator must provision an independent Fernet key as
`PLATFORM_MFA_KEY` in the protected API environment (or existing protected
configuration). It is a masked `SecretStr` setting. There is **no default key**,
no derivation from JWT credentials, and no key generated or installed by this
work. Missing/invalid key fails closed with 503. Back up this key securely with
restricted access separately from application backups. Replacing it without a
reviewed re-encryption/recovery procedure locks out existing MFA accounts.
Protect initial administrator credentials and verify intended recipients before
enrollment. Challenge/secrets are never written to browser persistent storage;
all platform responses use `Cache-Control: no-store`.

The existing bootstrap CLI remains for authorized local provisioning. Platform
factor recovery is `python -m scripts.recover_platform_mfa EMAIL`; it was tested
only with isolated fixtures. It is not a deployment/startup action. Business
password recovery still requires a separately approved owner identity and
delivery procedure; this console intentionally only opens the audited review.

Support has read-only platform access, billing retains only existing billing
writes, and super admin owns management writes. Platform role changes do not
alter employee permissions or business credentials. Platform administration is
not tenant impersonation. Revocation cannot remotely prove a client queue is
empty; retain explicit operator confirmation and existing offline policy.

## Migration and recovery

Only new migration: `p9b_fiscal_protocol → p10a_platform_management`.
Adds encrypted MFA fields to existing administrators, an assurance flag to
existing sessions, short-lived challenges and a single versioned settings row.
No duplicate subscription/license/billing tables. No tenant financial updates or
backfill. No shift enforcement/currency changes. Runtime grants only cover the
new platform tables, no schema CREATE/ownership changes.

Rehearsal used the **existing** isolated archived clone
`apexretail_phase7e_stabilization_clone_20261020` and existing test databases.
Upgrade, empty-state downgrade and forward recovery passed. All 34 historical
baseline tables / 809 rows retained identical canonical content hashes at every
step. This archive is not a fresh production backup; no current-production
compatibility/backup assertion is made. Full prior migration history was retained.
Downgrade refuses enrolled MFA, challenge, verified-session or settings records;
after use, plan reviewed forward recovery, not destructive rollback. A test
explicitly verifies the refusal with enrolled administrator data.

Future approved release needs a fresh verified backup, current production
revision/privilege checks, complete pending-chain rehearsal on its isolated
restore, secure MFA key provisioning, and coordinated backend/Backoffice switch.
Do not restart an old platform backend after new security records without a
reviewed compatibility plan. Tenant API and Android contracts were not changed;
platform login intentionally now uses the matching MFA-aware console.

## Verification evidence

Evidence directory: `artifacts/phase10-platform/` (synthetic screenshots only).

- Full backend suite after fixing the outdated legacy test double: **485 tests
  and 187 subtests passed**, six existing warnings. No skips/failures reported.
- Earlier full run: 479 passed, one failed because `FakeSubscriptionDb` lacked
  the new optional settings lookup. Corrected the test double, not authentication
  or production logic. Preserved all old assertions.
- Final targeted platform/billing run: **42 tests and 18 subtests passed**,
  three pre-existing warnings, no skips. Also covers response no-cache headers,
  masked configuration-key loading, non-ASCII code rejection and serialized
  administrator authority rechecking. See final JUnit/log evidence.
- All **24** existing POS/Backoffice regression, lint and build commands passed.
  Existing lint warnings: POS 2, Backoffice 8; existing large-chunk build advisory.
- **16** new responsive console/browser checks passed (320/390/820/1440px,
  separate pages, MFA UI, role restrictions, settings save and recovery review).
- **13** existing platform billing browser checks passed, including exact-original
  payment retry. Existing fixture now exercises the MFA screen.
- Browser data is synthetic; external network requests blocked. One initial
  browser test locator timed out on a select's computed accessible label; changed
  it to the appropriate combobox locator and the full browser run passed.

## Remaining acceptance / readiness

Not deployed. **NO-GO for unattended production release** until operational gates
above are satisfied and owner approves. Software results do not establish:

- Physical Android/WebView, authenticator-app, tablet or printer acceptance.
- Production browser/session rollout, TLS, reverse-proxy rate limiting or host monitoring.
- External email/SMS delivery: existing notices remain in-app; no delivery was fabricated.
- Automated owner-password recovery: manual identity verification/delivery remains required.
- Live fiscal device registration/submission or ZIMRA certification (Phase 9 gates remain).

Settings do not edit secrets, exchange rates, infrastructure or arbitrary runtime
configuration. Administrator listing is bounded at 200; business/device/fiscal
directories paginate. These are explicit operating boundaries, not hidden
promises of unrestricted platform control.
