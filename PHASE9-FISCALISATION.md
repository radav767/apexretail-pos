# Phase 9 — ZIMRA fiscalisation preparation

This is the initial foundation report. See [PHASE9-INTEGRATION.md](PHASE9-INTEGRATION.md)
for the subsequent protocol implementation, verification and current limitations.

Status: DEVELOPMENT FOUNDATION; NOT COMMISSIONED, NOT CERTIFIED, NOT PRODUCTION READY.

Continues Phase 8 `f13f62a2301f73bd4ceb0c519e7278bb80e61ac9` on branch
`phase9/zimra-fiscalisation`. Production, Android and existing queues are untouched.

## Official requirements review — 21 October 2026

Official sources checked (not third-party SDKs or marketing claims):

1. [FDMS API specification, official download](https://www.zimra.co.zw/downloads/category/9-domestic-taxes?download=3807:fiscalisation-apidocumentation).
   Retrieved cover: **Doc. No. v7.2, 77 pages**. PDF SHA-256:
   `a004a84a0e9c37afc3693b951c2f23fba8339a31e6458a0769cbc1b4d0e4ba8e`.
   This is the version linked by ZIMRA at review time, not proof that no newer
   specification or onboarding instructions exist. Obtain written confirmation.
2. [Official FDMS onboarding](https://www.zimra.co.zw/news/22-taxmans-corner/2307-compliance-with-the-zimra-fiscalisation-data-management-system-fdms).
3. [Public Notice 30/2025: buyer details](https://zimra.co.zw/public-notices?download=4340:public-notice-30-of-2025-buyer-details-on-fdms-fiscal-tax-invoice).
4. [ZIMRA fiscalisation overview](https://www.zimra.co.zw/domestic-taxes/corporate/fiscalisation-explained)
   is the starting point for statutory scope, not an eligibility decision by this software.

### Verified technical constraints

The specification defines device registration/CSR, mutual TLS, receipt signing,
fiscal days, serial counters, credit/debit references, fiscal print fields and
offline files. These are separate from POS authentication and cashier Z reports.
Receipt tax IDs/validity must follow FDMS configuration; no statutory rates are
seeded here. Offline operation requires the device's assigned mode and ordered
recovery, not merely the browser's offline flag. See specification §§2, 4, 7, 9–13.

Test host: `https://fdmsapitest.zimra.co.zw`; live host:
`https://fdmsapi.zimra.co.zw` (specification §7.2). Neither is configured in an
executable network adapter. The official test Swagger connection was reset by
the peer from this VPS; current HTTP paths/schema could not be confirmed.
No TLS bypass, registration, credential generation, day opening or fiscal submission
was attempted. The linked PDF contains inconsistent overview/method wording in
places (notably authentication exceptions and offline file timing); confirm the
current OpenAPI and permitted device mode with ZIMRA before implementation.

### Registration, credentials and approval gates

ZIMRA test onboarding must supply/confirm taxpayer identity, device ID and activation
key, registered model/version and test access. Registration uses a CSR and returns
a device certificate; device private keys must remain server-side. Do not reuse
POS token, entitlement or Android APK signing keys. No such fiscal credentials
have been provided or created in this work.

The official onboarding process requires test fiscal invoices, credit/debit notes
and successful fiscal-day closure, followed by ZIMRA validation/approval before
live registration. Source 3 additionally requires captured buyer details to be
transmitted; missing buyer TIN must not be invented. No approval has been obtained.

Outstanding clarification: current statutory scope per tenant, current approved
specification/OpenAPI, onboarding contacts, model registration process, taxpayer
tax/HS mappings, local-time handling, rounding vectors, offline timing ambiguities,
58/80mm fiscal print acceptance, device topology and formal evidence required.
Do not present this report as tax/legal advice or a certification determination.

## Implemented development scope

- Additive migration `p8a_commercial_billing → p9a_fiscal_preparation`.
  Three new tables only: `fiscal_configurations`, `fiscal_preparations`, `fiscal_audit`.
  No backfill, original table changes, exchange-rate changes or historical links.
- Owner-user-only, tenant-scoped APIs under `/api/fiscal/{company_id}`:
  `GET/PUT configuration`, `GET preparations`, `POST preparations/{sale_id}`,
  `GET audit`. Restricted user roles, POS employee sessions and cross-tenant requests
  cannot use these endpoints. Configuration branch/register ownership is checked.
- Draft registration metadata and effective-dated tax mappings. Exempt is distinct
  from zero-rated. These are **unverified drafts**, never applied to checkout.
- Credentials: accepts only an opaque tenant-scoped server reference, masked on
  reads. No private keys, certificates, activation keys, arbitrary URLs or filesystem
  paths are accepted. **Credential vault resolution/provisioning is not implemented.**
  Saving ordinary UI changes preserves an existing reference; explicit null clears
  only the reference, not external keys. There are no credentials on disk from this work.
- Versioned configuration edits and append-only fiscal audit with non-secret settings
  history. Runtime role has no UPDATE/DELETE on evidence; PostgreSQL triggers also
  protect snapshots/audit. Config and source preparation serialise on the tenant row.
- Manual immutable snapshots of owned sales/refunds and line tax values, without
  converting them to FDMS payloads. Original timestamps and refund references are
  retained, including nulls; no invented counters, timestamps, IDs, signs or totals.
  One preparation per tenant/sale, enforced by lock plus unique constraint.
  SHA-256 detects unexpected snapshot changes. Nothing is automatically backfilled.
- Decimal-only tax diagnostics and partial receipt-total preflight tests.
  These helpers are not the sales tax engine and do not validate fiscal signatures,
  tax identities, HS/buyer details, original-note limits or fiscal numbering.
- Adapter protocol plus fail-closed uncommissioned adapter. All its calls fail
  without sending a request; there is no environment toggle to enable live submission.
- Backoffice → Settings → Fiscalisation: draft setup, gate/status display,
  source-review preparation and latest 50 audit events. Approved dark-green layout
  retained. No false remote health/success, valid QR or approval badge is displayed.

## Integration architecture and deliberately unfinished scope

Existing sale, refund, stock, shifts, reports and printing paths are unchanged.
Preparation is explicit and separate; it does not re-fiscalise historical records.
The module currently supports **one pilot fiscal register configuration per tenant**.
Multi-device commissioning and reconfiguration while receipts are pending need a
reviewed per-device lifecycle before activation.

After approved test access, extend the adapter with verified HTTP methods/paths,
TLS validation and tenant-isolated secret resolution. Add signed device/day state,
transactional ordered outbox and immutable attempt/acknowledgement records before
connecting new-sale events. Workers must send the same signed device/global/hash
identity on uncertain retries, never allocate another invoice after a timeout.
Serialize numbering/signature chains per fiscal device, not per cashier shift.
Reconcile FDMS acceptance **and validation errors**, not HTTP 200 alone.

Refund integration requires the actual accepted original fiscal reference, matching
tax/currency and cumulative credit limits. Never synthesize references for old sales.
Buyer/HS mappings, tips/service-charge treatment, multi-currency receipts and rounding
must be tested against approved FDMS examples before any payload mapper is accepted.
Fiscal receipt layout/QR, day counters/reports, certificate rotation, offline files,
status polling and failure recovery remain **not implemented/not accepted**.
Do not claim this is a functioning or approved fiscal transaction integration.

Offline POS queues remain unchanged. Tests verify preparatory snapshots retain source
identity/timestamps and duplicate calls do not create more records; **they do not prove
FDMS offline recovery**. No fiscal receipt is issued offline by this module.

## Verification and safety

Final development checks:

- Full backend suite: **446 passed, 175 subtests passed, no failures or skips**;
  six existing deprecation warnings (Starlette/httpx, Pydantic and two test escapes).
- Targeted fiscal suite: **16 passed, 17 subtests passed**; three existing Pydantic
  warnings. Final targeted rerun also checks audit configuration redaction/history.
- POS and Backoffice: **24 existing regression/lint/build commands passed**.
  Ten existing lint warnings and large-bundle advisories remain, no lint/build errors.
  An initial sandbox run reported child-process EPERM despite zero statuses;
  it was discarded and rerun successfully with error-aware result checking.
- Synthetic fiscal-settings browser suite: **9 checks passed**, including four widths
  (1440, 820, 390, 320), draft save, invalid JSON, denied-role editor, and no remote
  submission controls/external requests/uncaught errors. Not actual FDMS testing.
- Existing archived clone: upgrade `p8a → p9a`, downgrade `p9a → p8a`, forward recovery
  `p8a → p9a` passed. All 34 original tables/809 rows retained identical content hashes.
  All nine existing synthetic fixture databases upgraded successfully.
- Verified archived backup SHA-256:
  `da9b191138ff052d48860359efc4ac850f5d5b805cdc2918e3b22e40db0c6e36`.
  No fresh production backup was taken, and current production was not queried.

See generated evidence in `artifacts/phase9-fiscal/` and the delivery verification
report for final command results. Tests use existing disposable databases, rollback
fixtures and synthetic browser adapters; no new staging environment is created.
Migration rehearsal uses the existing archived production-backup clone, not live
production or a new production backup. Baseline is 34 historical tables/809 rows.
Empty-table downgrade is permitted; any fiscal configuration/evidence blocks downgrade
to prevent data loss. After use, recovery must be reviewed forward-only.

Physical fiscal receipts/QR, actual printer widths, Android device behavior, real FDMS
test communication, live environment approval and business-specific legal acceptance
are external/manual gates. No deployment or APK build is authorised by this work.

**Release decision: NO-GO for fiscal production activation.** The tested preparation
foundation may be reviewed independently; it is not a certified fiscal device.
