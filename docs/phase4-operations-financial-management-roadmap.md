# Phase 4 — Operations and Financial Management roadmap

Status: approved requirements translated into a read-only implementation plan.
No Phase 4 implementation is authorized by this document.

## Scope boundary

Phase 4 starts only after Phase 3 has passed its performance and release gates.
It must not be folded into the Phase 3 corrective commit. The work covers five
bounded capabilities:

1. grouped Sales History reporting;
2. cross-branch terminal administration and safe device retirement;
3. inventory valuation and margin reporting;
4. controlled expense accounting; and
5. credit-sale settlement.

Existing sales, receipts, refunds, inventory movements, settlement evidence, and
audit history are financial records. Phase 4 must extend them additively and must
not rewrite history to make new reporting fields appear complete.

## Cross-cutting design rules

- Every row and request is company-scoped. Branch/shop identifiers must belong
  to the authenticated company before any read or write.
- Money uses fixed-precision decimals and an explicit currency. Quantities keep
  the existing three-decimal behavior where applicable. Never use binary floats.
- Posted financial events are immutable. Corrections use linked reversal or void
  records, never hard deletion or in-place amount replacement.
- Every mutation accepts an idempotency key, executes in one database
  transaction, and creates an audit event in that transaction.
- Reports, drill-downs, and exports share one canonical filtered population so
  totals and permissions cannot diverge.
- Unknown historical facts remain `Unavailable` with a machine-readable reason;
  they are never silently converted to zero.
- Device authorization is deny-by-default after reassignment, decommission, or
  removal, including offline tokens and queued synchronization.

## Delivery sequence

Implement as separately reviewable slices:

1. shared permissions, immutable audit envelope, idempotency conventions, and
   report/export contracts;
2. Sales History reporting views;
3. device reassignment and decommissioning, followed only then by any approved
   permanent-removal behavior;
4. inventory valuation after formula approval;
5. expenses through posting/reversal, initially excluded from net profit; and
6. credit settlements after accounting and offline policy approval.

Each slice gets its own migration, compatibility window, validation evidence,
deployment decision, and rollback plan. Do not bundle all Phase 4 migrations
into one irreversible release.

## 1. Sales History reporting views

### Product behavior

Add a labelled `View / Group` dropdown to Backoffice Sales History with:

- All sales;
- Sales by cashier;
- Sales by product;
- Sales by category;
- Sales by payment type;
- Sales by branch/shop;
- Credit sales;
- Discounts;
- Refunds; and
- Voids.

Keep date, branch/shop, cashier, product, payment, and status filters visible and
stable when the view changes. A grouped row opens a drill-down carrying the exact
same normalized filters. CSV export invokes the same service/repository result as
the screen; it may stream rows but cannot reimplement totals.

### Database

Prefer existing immutable sale and sale-item snapshots. Add only fields needed
to represent approved void semantics, such as `voided_at`, `voided_by`,
`void_reason`, and a reference to a compensating record. Do not infer voids from
deletion flags. Preserve original product/category/cashier/shop/payment labels in
snapshots so renamed master data does not rewrite historical reports.

Assess selective indexes using real isolated plans for company plus date, with
optional shop, employee, payment, status, original-sale, product, and category
filters. Add no index without before/after evidence.

### Backend

Define one normalized filter object and one canonical accounting population.
Expose a versioned report endpoint with a `view` enum, pagination cursor or
stable offset contract, deterministic ordering, and a matching export endpoint.
Grouped results include metric availability metadata and drill-down filter
tokens. Enforce existing reports/refunds permissions plus any separately
approved void permission.

### Backoffice

Use an accessible native select or equivalent labelled combobox. Preserve filter
state in the URL so refresh/export/drill-down are reproducible. Show active
filters, reporting timezone, currency, empty/error/loading states, unknown metric
reasons, stable pagination, and spreadsheet-safe export behavior. Group views
must work at 320 px and 390 px and with keyboard-only navigation.

### POS and Android/offline

Do not add the grouped management reports to the cashier POS. POS may retain its
operational receipt lookup, reprint, and authorized refund workflows. Existing
offline sales must continue to sync their immutable snapshots; a newer server
must accept the currently released APK payload throughout the compatibility
window.

### Tests

Reconcile every grouped total to All sales for mixed completed, partially
refunded, refunded, credit, discounted, and voided fixtures. Cover timezone
boundaries, renamed/deleted dimensions, unknown discounts, cross-company IDs,
permissions, stable pagination, CSV injection escaping, and identical screen /
drill-down / export populations.

## 2. Devices/POS management

### State model and database

Treat terminal assignment, device identity, sessions, and offline authority as
distinct records. Add an append-only `device_assignment_history` or generic
immutable security-event table containing company, device, old/new shop and
branch, actor, reason, effective timestamp, request/idempotency ID, and safe
before/after metadata.

Add explicit retirement state such as `decommissioned_at`,
`decommissioned_by`, and `decommission_reason`. If permanent removal is approved,
use a tombstone/key-revocation design unless legal and referential analysis proves
physical row deletion is safe. Historical sales may retain the device ID or a
non-sensitive terminal snapshot; no foreign key may cascade from devices into
sales, receipts, settlements, inventory, or audit events.

### Reassignment transaction

An owner/authorized administrator chooses any active branch/shop in the same
company. The API locks the device and relevant active sessions, verifies the
target hierarchy, records old/new assignment, revokes current sessions and
offline credentials, rotates the server-side device identity/epoch, applies the
assignment, writes the immutable audit event, and commits atomically.

The UI must display the current branch, destination, affected active operator,
and consequences: forced sign-in, queued offline work requiring resolution, and
new branch inventory/sale attribution. Reassignment never rewrites historical
sales or inventory movements to the new branch.

### Permanent removal and secure decommission

Before removal, calculate blockers: unsynced batches, active sessions, pending
activation/settlement requests, unresolved handovers, legal-retention links, and
referential dependencies. If any blocker makes deletion unsafe, return a typed
conflict listing what must be resolved. Never bypass it with cascading deletes.

Secure decommission is the mandatory fallback and should be implemented first.
It immediately:

- marks the terminal inactive and non-billable according to the approved billing
  policy;
- revokes all sessions and refresh/offline tokens;
- rotates or tombstones the device key and increments an authorization epoch;
- rejects future heartbeat, activation, sale sync, and settlement sync attempts;
- clears the live terminal assignment while preserving its assignment history;
  and
- preserves every financial and audit reference.

Permanent deletion, if later approved, requires an explicit typed confirmation
containing the terminal name/number, recent reauthentication, elevated
permission, zero blockers, and an immutable audit tombstone that survives the
device row. It must be impossible to reuse the revoked identity.

### Backend, Backoffice, POS, and offline

Provide separate endpoints for previewing consequences, reassigning,
decommissioning, and—only if approved—permanently removing. Never overload the
ordinary device-update endpoint. Backoffice presents a review screen followed by
explicit confirmation. POS detects epoch/revocation responses, locks protected
actions, preserves but does not upload quarantined queues, and directs an
administrator to resolve them. Define whether verified queued sales must sync
before reassignment; do not silently reattribute them.

### Tests

Cover concurrent reassignment, stale idempotency retries, cross-company targets,
active sessions, key reuse, offline replay after revocation, billing counts,
foreign-key blockers, audit immutability, historical receipt readability, and
transaction rollback at every write boundary.

## 3. Inventory valuation and margin

### Ambiguity requiring approval

The current vocabulary does not prove that `cost_price`, “buying price,”
`selling_price`, and “retail price” have one universal meaning. Before formulas
are implemented, approve:

- whether cost means latest purchase cost, weighted-average cost, FIFO cost,
  standard cost, or another method;
- whether tax, freight, landed costs, supplier discounts, and currency conversion
  are included in cost;
- whether selling value uses the current list price or a historical/branch price;
- whether stock is valued by product totals or authoritative branch balances;
- treatment of negative stock, damaged/quarantined stock, returns, and fractional
  quantities; and
- whether margin percentage is `(selling value - cost value) / selling value` or
  markup is `(selling value - cost value) / cost value`.

Recommended starting definition, subject to approval: authoritative branch
quantity on hand multiplied by a persisted weighted-average unit cost; projected
selling value uses the current branch selling price; projected gross profit is
selling value minus cost value; margin percentage divides projected gross profit
by selling value. Label this as projected inventory margin, not realized profit.

### Metrics and availability

Report separately:

- quantity on hand;
- cost value;
- selling value;
- projected gross profit; and
- margin percentage.

Each monetary metric carries `available`, `value`, `reason`, and
`missing_persistence`. If any contributing positive/negative quantity lacks the
required cost or selling snapshot, the dependent aggregate is unavailable.
Zero quantity may produce known zero value only when the formula has no unknown
contribution. A zero selling-value denominator makes margin percentage
unavailable, not zero.

### Database and backend

After formula approval, persist the required cost layers or weighted-average
snapshots per company/product/branch and immutable valuation movements. Do not
retroactively fabricate missing costs. Provide versioned Backoffice-only summary,
detail, drill-down, and export endpoints with branch/category/product filters and
an `as_of` timestamp. Keep calculation code centralized and decimal-safe.

### Backoffice, POS, Android/offline

Backoffice requires a dedicated valuation permission in addition to inventory
access, because cost and margin are commercially sensitive. Remove stock value,
cost value, projected profit, and margin from cashier-facing POS navigation and
responses. POS retains quantities needed for selling and stock operations.
Android must not cache valuation responses or embed cost/margin data in offline
bundles available to cashiers.

### Tests

Use hand-calculated fixtures for the approved cost method, cross-branch totals,
unknown cost propagation, zero/negative quantities, returns, tax/rounding,
concurrent receipts/transfers, authorization, export equality, and absence of
valuation data from POS/API payloads and offline storage.

## 4. Expense module

### Database

Use additive normalized tables:

- `expense_categories` scoped to company;
- `suppliers_payees` scoped to company, with optional contact/tax metadata;
- `expenses` with company, branch/shop, category, payee, expense date, currency,
  net amount, tax amount, gross amount, payment method, reference, notes, status,
  creator/approver, timestamps, and idempotency key;
- `expense_attachments` containing storage object ID, content hash, media type,
  size, uploader, and malware-scan state—not arbitrary server paths; and
- `expense_events` or the shared immutable audit envelope for submit, approve,
  reject, edit-draft, post, void, and reverse events.

Statuses should be explicit: draft, submitted, approved, posted, rejected,
voided/reversed. Posted rows are immutable. A correction creates a linked,
equal-and-opposite reversal and optionally a new replacement expense. Hard-delete
may be allowed only for an unsubmitted draft if audit/legal policy approves it.

### Backend

Separate create/edit draft, submit, approve/reject, post, reversal, attachment,
detail, report, and export operations. Enforce valid state transitions and
separation-of-duties rules. Validate branch, category, payee, payment method,
currency, amount/tax arithmetic, reference uniqueness policy, attachment type /
size/hash, and company ownership inside the transaction.

Net-profit reporting initially excludes expenses and says so explicitly. Include
them only after approval of the accounting definition: recognition date, status
included, tax treatment, refunds/reimbursements, owner drawings, capital assets,
cost of goods overlap, multi-currency conversion, and treatment of reversals.

### Backoffice

Provide queue, entry, approval, detail/audit timeline, attachment preview, void /
reversal, and reports. Show status and permissions in text, require reasons for
reject/reverse actions, prevent editing posted values, and make attachment
failures recoverable without duplicating the expense.

### POS and Android/offline

Default scope is Backoffice-only. Do not add cashier expense entry or store
receipt attachments offline without a separate approval. If later required,
define encrypted storage, upload retry/idempotency, handover ownership, and what
happens when approval or device access is revoked.

### Security and tests

Use private object storage, signed short-lived download authorization, malware
scanning, strict media sniffing, encryption, and retention policies. Test every
state transition, amount invariant, permission, separation of duties,
cross-company reference, duplicate request, concurrent approval, attachment
attack, reversal chain, immutable posted row, report/export reconciliation, and
transaction rollback.

## 5. Credit-sales settlement

### Accounting and state model

The original credit sale remains an immutable sale. Settlements are separate
financial events linked to it; recording payment must never alter or erase the
sale, its tender snapshot, items, receipt, or original totals.

Add company-scoped customers/debtors only after approving required identity and
privacy fields. Add a credit account or sale-credit record with original sale,
debtor, original amount due, due date, currency, and status. Add immutable
settlement records with amount, method, reference, received timestamp, branch,
cashier/session/device, idempotency key, receipt number, and optional reversal-of
link. Derive paid and outstanding amounts from posted settlements minus posted
reversals, or maintain a locked validated projection that reconciles to that
ledger.

Statuses should be derived from invariant amounts: unpaid, partially paid, paid,
overdue, and reversed/void where defined. In one locked transaction, enforce
`0 < payment <= outstanding`, matching currency/company, active authorization,
unique idempotency key, and one settlement receipt per committed event.

### Backend

Provide credit-sale search/detail, settlement preview, create settlement,
settlement receipt, reversal, debtor statement, aging report, drill-down, and
export endpoints. Lock the credit account/original sale during settlement;
recalculate outstanding inside the lock rather than trusting a client balance.
Duplicate retries return the original committed response. Reversal cannot exceed
the settlement’s unreversed amount and never deletes the settlement.

### Permissions and cashier handover

Approve separate permissions for viewing debtor data, accepting settlements,
reversing settlements, exporting statements, and managing customers. Define
whether cashiers may settle credit issued at another branch, how cash/card/mobile
settlements enter shift totals, who owns a settlement after handover, and whether
manager approval is required for reversal or overdue exceptions.

### POS, Android, and offline

Recommended initial policy: online-only settlements. The client may view a
recent cached balance as informational but must obtain and lock the authoritative
server balance before accepting payment. This avoids two devices independently
spending the same outstanding balance.

If offline settlement is approved later, it needs a risk protocol: server-issued
single-use spend authority with amount/expiry/device/customer bounds, encrypted
queue, deterministic idempotency key, signed receipt status, conflict handling,
cashier liability/handover, and a rule for rejecting or escalating settlements
whose authority was consumed elsewhere. Ordinary offline sale sync is not enough.

### Accounting definition requiring approval

Approve whether the original credit sale recognizes revenue/tax/cost at sale
time and settlement affects only receivables/cash, or whether local policy uses a
cash basis. Define discounts, interest/fees, bad debt, write-offs, refunds against
partially settled sales, settlement-method fees, overpayment handling (recommended:
reject), and aging timezone. Dashboard sales totals must not count settlement
cash as a second sale.

### Tests

Cover partial/full sequences, mixed methods, simultaneous devices, exact retry,
overpayment, reversal/re-settlement, cross-company and cross-branch policy,
expired permissions/session/device, receipt uniqueness, refund interaction,
cashier handover, offline denial or approved authority behavior, migration of
historical credit sales, ledger/projection reconciliation, and unchanged original
sale fingerprints.

## Security design

- Add narrowly scoped permissions rather than relying only on broad administrator
  labels. Owner bypass behavior must be explicit and tested.
- Require recent reauthentication for permanent removal, expense reversal, and
  high-risk settlement reversal.
- Store idempotency keys with company, actor/device, operation type, request hash,
  status, and canonical response; reject key reuse with a different request.
- Make audit events append-only at both service and database privilege levels.
  Include actor, company, device/session, request ID, reason, timestamp, and safe
  before/after metadata. Never store tokens, keys, attachment contents, or excess
  personal data in audit JSON.
- Apply rate limits to device security actions, debtor search, attachment upload,
  and settlement attempts. Log denied cross-company access without disclosing the
  target record.
- Encrypt private attachments and sensitive debtor fields, define retention and
  deletion obligations, and exclude them from general exports/backups where
  policy requires.

## Testing strategy

Every slice requires:

- unit tests for formulas, states, availability, and permission matrices;
- PostgreSQL integration tests using strictly named isolated databases;
- migration tests from the currently deployed revision, fresh install, downgrade
  where lossless, and re-upgrade;
- transaction fault injection proving no partial balances, revocations, postings,
  or audit records;
- concurrency tests for device moves, expense approval/reversal, and settlement;
- contract tests against the released POS/Android payload;
- Backoffice component, keyboard, 320/390 px, empty/error/loading, drill-down, and
  export tests;
- Android/offline upgrade, queue replay, revocation, storage, and retry tests;
- tenant-isolation and insecure-direct-object-reference tests; and
- representative `EXPLAIN ANALYZE` evidence for every new report population.

Financial fixtures must reconcile independently calculated totals across screen,
drill-down, CSV, receipts, and ledgers. Tests must assert that historical rows are
unchanged after migrations and reversals.

## Deployment design

1. Freeze and approve one slice and its unresolved decisions.
2. Produce an exact commit and dependency/build manifest.
3. Take a snapshot-consistent, encrypted, checksum-verified backup and validate
   it by restoring into a new isolated database.
4. Validate migration from the deployed revision, semantic financial invariants,
   downgrade/re-upgrade where safe, full backend/frontend compatibility, and
   representative plans.
5. Deploy additive schema before clients that write new fields. Keep old payloads
   accepted through a documented compatibility window.
6. Deploy backend, run local authenticated semantic smoke checks, then publish
   Backoffice assets. Publish POS/Android only for slices that actually change
   those clients and only with separate signing/version approval.
7. Enable risky behavior behind server-side company/permission flags: valuation,
   expense posting, settlement, and permanent device removal should not all turn
   on at once.
8. Record exact revisions, checksums, smoke results, audit-event checks, and
   monitoring links. Observe errors, latency, balance reconciliation, offline
   rejections, and duplicate/idempotency conflicts before widening rollout.

## Rollback design

Prefer feature disablement and a reviewed forward fix. Do not automatically
restore production or run destructive downgrades.

- Reporting UI/API: disable the new view flag and restore compatible assets;
  additive report fields/tables may remain.
- Device actions: disable reassignment/removal endpoints. Revoked identities stay
  revoked unless a separately audited recovery flow issues a new identity. Never
  resurrect a deleted key from backup.
- Valuation: disable display/calculation jobs; preserve cost-layer evidence.
- Expenses: disable new posting while retaining read/reversal access. Never delete
  posted expenses to roll back an application release.
- Settlements: disable new settlement acceptance while retaining receipt,
  statement, reconciliation, and controlled reversal access. Never restore a
  snapshot over newer payments.

Before any schema downgrade, prove it is additive and lossless on a restored
clone containing post-release writes. If a downgrade would discard expenses,
settlements, audit history, revocations, assignments, or valuation layers, it is
not an operational rollback. Keep the schema, deploy compatible code, and prepare
a separately approved data migration if needed.

## Decisions requiring explicit approval

The following block implementation beyond schema/prototype work:

1. Inventory cost method and meanings of cost/buying/selling/retail price.
2. Tax, landed-cost, currency, negative-stock, and margin-percentage rules.
3. Device “permanent removal”: tombstone versus physical deletion, dependency
   blockers, offline-queue treatment, billing effect, confirmation text,
   reauthentication, and retention period.
4. Whether queued offline sales must sync before terminal reassignment and how
   their original branch attribution is preserved.
5. Formal void semantics and which records/actions constitute a void.
6. Expense approval thresholds, separation of duties, tax/currency treatment,
   attachment retention, and the precise net-profit definition.
7. Credit-sale revenue/tax recognition, debtor data requirements, settlement
   permissions, branch/cashier handover, refund/write-off rules, and online-only
   versus controlled-offline settlement.
8. Audit retention, immutability enforcement, sensitive metadata policy, and who
   may export each financial dataset.
9. Compatibility duration for the currently released Android/POS client and
   rollout/feature-flag order for each Phase 4 slice.
