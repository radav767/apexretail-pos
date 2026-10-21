# Phase 9 — documented protocol integration (development only)

Continues verified commit `ad111602d992ee65ba4ad802589c7e0d22afe2a6` on
`phase9/zimra-fiscalisation`. No production deployment, production database access,
Android build, live fiscal transaction, or new staging system was performed.

## Specification and evidence

The [official ZIMRA download](https://www.zimra.co.zw/downloads/category/9-domestic-taxes?download=3807:fiscalisation-apidocumentation)
still identifies itself as **Fiscal Device Gateway API specification v7.2 (77 pages)**
when checked on 21 October 2026. This confirms the version available at that link,
not that ZIMRA has no newer private/onboarding revision. The existing downloaded
PDF SHA-256 is `a004a84a0e9c37afc3693b951c2f23fba8339a31e6458a0769cbc1b4d0e4ba8e`.

The official test Swagger page could not be fetched; a public documentation GET
from this VPS again ended with TLS connection reset. No certificate validation was
disabled. **Exact current HTTP paths, methods and parameter bindings remain unverified.**
The code does not guess them or implement a functioning direct HTTP adapter.

Sections used: §4 operation fields, §5 enums, §6 counters, §7 communication,
§9 device sequencing, §§10–11 print/QR fields, §13 canonical signatures.
Official onboarding remains [ZIMRA's published process](https://www.zimra.co.zw/news/22-taxmans-corner/2307-compliance-with-the-zimra-fiscalisation-data-management-system-fdms).

## Implemented and automatically verified scope

| Area | Implementation | Boundary |
| --- | --- | --- |
| Communication | Documented operation names, device/model/version binding, required headers, 30-second timeout contract, sanitised documented HTTP problem categories | Injected transport only; no actual FDMS HTTP mapping or requests |
| TLS/credentials | Hostname/server trust validation context, TLS minimum 1.2, root-owned protected per-tenant credential paths, no symlinks or arbitrary nested paths | Provisioning, FDMS issuer/CN validation, private-key storage/resolution and mTLS handshake remain commissioning work |
| Fiscal days | Persisted test-device bootstrap, open intent/ack, counters, pending close, status reconciliation, trusted closing-signature callback, maximum-day/certificate issuance guards | Fresh empty test device only; existing device history/manual close needs reviewed import/reconciliation |
| Signing | Exact ordered receipt/day canonical messages, SHA-256, cents, tax ordering, exempt versus zero, daily receipt hash chain, locally verified signer interface, trusted FDMS acknowledgement verifier interface | Real key provider, algorithm wire encoding, FDMS chain/rotation and conformance not commissioned; no guessed RSA padding |
| Receipts | Totals, quantities, prices, tax validity/identity, HS rules, buyer data, currency context, source timestamp/line/total binding, note references and cumulative credit checks | Strict manual test mapping only; not a complete automatic POS-to-FDMS mapper |
| Durable submission | Immutable signed payload, unique source/global identity, ordered dispatch, committed attempt before transmission, exact-payload retry after uncertain result | No public mutation endpoints; injected synthetic transport for tests only |
| Reconciliation | Trusted signature required for receipt acknowledgement and auto-close, unknown/rejected states retained, no HTTP-success-equals-valid assumption | HTTP 200/receipt ID is never called fiscal validity; crashed in-flight intents require reviewed recovery |
| Offline | Delayed day-open queue in Online device mode, cached configuration, persistent receipt preparation, opening-before-receipts recovery; complete single closed-day Offline-mode file builder with checked signatures, chain/counters and exact JSON decimals | No first-time offline commissioning, automatic Offline-mode uploader or automatic file splitting; contradictory file timing text awaits clarification |
| Formatting | Escaped 58mm/80mm/A4 review HTML with taxpayer, branch, device, buyer, original note reference, items, payments, quantity and tax blocks; documented QR URL assembly from supplied verified QR data | Always visibly TEST/REVIEW; no valid fiscal QR, approved fiscal print path, PDF integration or physical printer acceptance |
| POS / Backoffice | Receipt fiscal status lookup scoped to existing sale permissions and branch; owner-only protocol report and sandboxed review viewer | Read-only fiscal integration, not automatic fiscal issuance during checkout |

No tax rates are seeded. Tax diagnostics do not alter checkout calculations.
Their rounding convention still requires approved FDMS test vectors. Source rows
with missing currency/timezone, unsupported discounts/extra charges or mismatched
line/tax totals are rejected, never repaired by inventing fiscal data. A multi-currency
sale with non-base tender must not be fiscalised by this pilot mapper without a
reviewed payment conversion/mapping policy. Tips and service-charge mapping also
remain subject to verified taxpayer tax treatment; no existing totals are changed.

### Reliability and audit rules

One pilot register per business remains supported. A device channel must match the
business's configured model/version/device and **test** environment. Production
channels are rejected. All public fiscal mutation paths remain absent; the original
uncommissioned adapter remains the default. No environmental toggle activates live FDMS.

Protocol operations serialize on the company row. Device/global numbering and source
preparations have database uniqueness constraints. Signed payloads/events are append-only,
protected by triggers and runtime-role privileges. Every protocol event also writes the
existing fiscal audit with the initiating owner identity. Configuration is frozen once
protocol state exists, so changing identity cannot silently repoint pending receipts.
Test-device bootstrap also uses a transaction-level device-namespace advisory lock and
rejects a device already claimed by another business's protocol, so two tenant drafts
cannot independently allocate numbers against the same test device.

Committed intents survive process failure. A response lost after submission does not
cause a new invoice: retry uses the identical immutable receipt. Only a trusted receipt
signature records acknowledgement. A definite 4xx rejection is not retried as a network
outage. Unknown outcomes are `submitted: null`, not falsely reported as unsent.
An unresolved predecessor blocks later receipt dispatch and day closure.

Client offline queues are not rewritten or deleted. These tests cover server-side
FDMS-outage recovery using synthetic persisted source records; they do **not** establish
end-to-end Android fiscal issuance. No sale, payment or stock deduction is made by this
module. No cashier-shift report is relabelled as a fiscal-day report.

## Official fixture findings / clarification gates

- §13.2.1 CreditNote example 2 reproduces its published SHA-256 value exactly.
- Both §11 QR URL assembly examples match. Actual QR-data derivation remains withheld:
  a paired device-signature/QR vector is needed to resolve the MD5-input wording.
- The printed FiscalInvoice example 1 concatenation hashes to
  `eHAAOVqxrRVRliVOsik4sONXJ10nckqCWIhPyoMyguM=`, not its printed
  `zDxEalWUpwX2BcsYxRUAEfY/13OaCrTwDt01So3a6uU=`. This discrepancy is
  recorded in an explicit regression test, not silently “fixed” or counted as conformance.
- The Offline file example has inconsistent inclusive line/tax/total figures, and
  fiscal-day examples contain sorting/text inconsistencies. Do not use these as
  complete valid fiscal fixtures without ZIMRA clarification.
- Certificate signature encoding, authoritative rounding vectors, permitted
  header-only/open-day Offline files and approved physical layouts need confirmation.

## Migrations and safety

New additive migration: `p9a_fiscal_preparation → p9b_fiscal_protocol`.
New tables only: `fiscal_protocol_states`, `fiscal_documents`, `fiscal_protocol_events`.
Existing tables, deployed migrations, currency settings and historical records are unchanged.
There are no data backfills or invented historical fiscal associations.

The existing archived restored-production clone and all nine existing disposable fixtures
were upgraded. Clone upgrade → empty-table downgrade → forward recovery passed;
all **34 historical tables / 809 rows retained identical content hashes** at every step.
This is archived-clone evidence, not verification against current live production data.
Populated fiscal-protocol downgrade is refused; use reviewed forward recovery.

## Test evidence

- Broad backend regression: **469 tests and 181 subtests passed**, no failures/skips;
  six existing deprecation warnings. A final targeted fiscal run checks the additional
  cross-business namespace guard introduced after the broad run started.
- Final targeted fiscal suite: **39 tests and 23 subtests passed**, no failures/skips;
  three existing Pydantic deprecation warnings.
- All **24 existing POS/Backoffice regression, lint and build commands passed**;
  ten existing lint warnings and bundle-size advisories remain, with no errors.
- **14 synthetic browser checks passed**, including four screen widths, permissions,
  draft settings, POS fiscal status/uncertainty, and actual backend-generated review HTML
  rendered at 58mm, 80mm and A4. No external requests or uncaught browser errors occurred.
- `p9b` archived-clone upgrade/downgrade/forward recovery and nine fixture upgrades passed;
  historical content hashes remained unchanged throughout.

Final results are recorded with the committed source hash in
`artifacts/phase9-fiscal-integration/` and the persistent delivery evidence directory.
Full backend regression, targeted fiscal tests, existing POS/Backoffice tests/builds,
and loopback-only synthetic browser checks are run. Any preliminary failing runs
were investigated rather than reported as successful; final results supersede them.

Official vectors are distinguished from synthetic fixtures. Synthetic acknowledgements
use **ephemeral in-memory test keys**, not real FDMS certificates or the public PDF's
example private keys. They prove local recovery/verification mechanics, not FDMS approval.
Receipt screenshots are browser renders of the backend's synthetic review HTML, not
photographs or physical printer tests. No printed, Android or real FDMS test is claimed.

## Remaining external requirements and software commissioning work

1. Obtain current official OpenAPI and clarify the documented inconsistencies.
2. ZIMRA test onboarding: registered taxpayer/branch/device/model/version, activation
   credentials, approved test access, and confirmed allowed currencies/tax/HS mappings.
3. Reviewed tenant-isolated key provider, CSR/registration/renewal implementation,
   device/server trust chains, signature encoding and certificate rotation.
4. Implement the exact verified HTTP adapter and test it against the authorised test
   service. No network interoperability test has yet been possible.
5. Complete and verify automatic sale/refund, discounts, buyer/HS, tips/service charge,
   tender/currency and receipt-print mapping. This pilot deliberately refuses uncertain
   mappings; it must not be described as a complete fiscal checkout integration.
6. Review multi-register/device topology, migration of pre-existing fiscal device state,
   manual fiscal-day exception recovery, heartbeat/expiry alert scheduling, Offline-mode
   file sequencing/upload/status handling and end-to-end Android recovery.
7. Obtain sample invoice/credit/debit-note validation and successful fiscal-day closure
   acceptance from ZIMRA, followed by formal live registration/approval. Physical receipt
   widths/QR scans and real printer/Android tests remain pending.

**Decision: NO-GO for production fiscal activation.** This is a verified local test
protocol and read-only integration, not a certified fiscal device or functioning live
FDMS connector. Production activation requires separate approval after commissioning.
