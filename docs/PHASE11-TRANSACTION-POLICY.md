# Phase 11 transaction, replay and disconnected-operation policy

Development policy established before guard changes, continuing from 9656d1a. This is a tested implementation target, not production approval or a change to legacy commercial pricing. Super Admin remains NO-GO.

| Request class | Authorization and license decision | Effects |
| --- | --- | --- |
| Historical sales, financial reports, receipt/fiscal evidence and committed-command recovery | Current authenticated identity, current tenant/branch/register and domain permission checks remain mandatory. Expiry, suspension or a later module downgrade alone must not hide existing business records. | Return existing records. Explicit receipt audit/delivery and reviewed acknowledgement may persist their existing document identity; no new sale, stock movement, payment or fiscal transaction. |
| Exact committed sale/operation replay | Verify original actor/context and durable canonical command fingerprint. Current identity revocation/branch/device restrictions still apply. Only then bypass current write-license/module checks. | Return original result; do not rerun stock, price, tax, credit, approval, payment or delivery effects. A duplicate command never becomes a new transaction. |
| Legacy committed sale without a trustworthy request fingerprint | Tenant/branch/receipt permissions still permit read-only lookup. Do not invent a fingerprint from incomplete historical snapshots. | POST identity reuse returns conflict and directs the client to original-result lookup/review; no automatic resubmission or reconstruction. |
| New online write or uncommitted queued sale/operation | Current identity/permissions and current server subscription/module policy required. A missing subscription is not a license. Client timestamps, cached status or signed offline-shift attribution alone cannot override the current server decision. | One atomic business mutation and its command receipt. Queued items rejected with 402/403/409 remain intact for renewal/re-authentication or explicit review. No timestamp substitution, deletion or silent recapture. |
| Financial correction, configuration, stock or optional-module change | A new mutation requires current domain authority and write license; historical correction exceptions must be explicit per operation. No blanket expiry bypass for refunds/settlements. | Existing domain constraints/idempotency continue. Operations without durable replay proof must not claim exact replay support. |
| Authentication/logout/reset/renewal, security decommission, historical fiscal preparation or existing receipt delivery | Existing dedicated identity/proof/role checks; no renewal requirement just to revoke access, authenticate, read history or prepare existing evidence. Real provider actions remain disabled/gated. | No implicit sale/payment/stock mutation. All existing revocation and recovery gates survive rollback. |

## Decision and transaction boundaries

License authorization is a fresh server read at the new-command decision point. A later expiry/suspension does not cancel a command already authorized in flight; subsequent new commands observe the new state. This is an explicit linearization policy, not a claim of immediate cancellation across concurrent requests. A wall-clock timestamp supplied by a browser does not prove that a queue was licensed when captured.

Serialize equal command identities before checking receipts; persist fingerprint/result bindings in the SAME transaction as stock/payment effects. Do not allow helper-level commits to release command locks midway. Canonical fingerprints include business input and capture time; transient bearer/device/manager-approval credentials are not stored. Scope bindings and current credential checks remain independent of the fingerprint. Different actors, changed quantities/tenders/currency/discounts or a reused identity without proof fail closed. Generated UUID identities remain globally unique where the existing sales schema requires it.

Historic price/tax/customer/shift changes do not cause an exact committed command to be executed again. Return a verified committed receipt before attempting current-shift/price/credit revalidation, while still enforcing current actor/tenant/branch/register access. Active but expired accounts may retrieve evidence; inactive/deleted/revoked identities are not re-enabled by this exception.

## Bounded offline trust target

Signed entitlement maximum lifetime/grace remains an upper bound, never an extension after suspension. Browser-owned storage and wall clock are not tamper-resistant. Require a verified signed server-time anchor, bounded elapsed-time lease and reconnect on rollback, unexplained restart/anchor loss or lease expiry; never erase queued records. A disconnected device cannot learn immediate revocation. Production acceptance must state the maximum disconnected exposure and native/device trust assumptions rather than claim absolute clock/revocation resistance.

New queue upload after reconnect uses the current server write decision above. Existing offline-shift proofs continue to establish immutable attribution only. Closed shifts, moved/decommissioned registers and stale assignments retain their existing manager-review requirements. A rejected queue is not a failed committed transaction and must not be automatically discarded or charged again.

## Rollback

Any compatible application rollback must preserve user/session/employee revocation, canonical receipt matching, single-use credential/grant checks and queue retention. Never restore an older database over later sales, payments, acknowledgements or revocations. Additive migration downgrade must refuse to discard replay/revocation evidence; forward recovery is the default. No deployment or production migration is authorized.
