# Phase 7 final development — verified fixes, release acceptance still pending

Continues the existing `phase7g/android-shift-acceptance` branch from
`75fbb574f344b2d0f6dee9618e03ac207e7e6554`. No new project, application,
database, staging environment, APK, production deployment or production write.
The resulting development commit is recorded in the accompanying evidence.

## Implemented fixes

- POS product management now distinguishes Add, Edit, Delete/Archive and cost
  permissions. Explicit granular denials override the broad legacy alias.
  The previously missing Archive action uses the existing protected API and
  preserves stored stock and financial history.
- POS and Backoffice variants now support edit, archive and restore. Editing
  metadata does not resubmit an absolute stock quantity or overwrite attributes.
  Blank inherited prices are labelled as inherited, not misleading zero prices.
- Both price-level pages now support edit and delete, not just creation.
  Mutation guards prevent same-view double submission; editors reset when the
  selected product changes. Stale detail fetches cannot overwrite a newer
  selection. Backoffice variant reads now include the selected branch instead
  of showing an unscoped zero balance.
- Restricted product costs are not sent by the POS editor. The backend protects
  both product and variant updates: an older client's redacted null cannot erase
  a stored restricted cost; unauthorized explicit non-null changes return 403.
  Authorized users may still explicitly clear an optional cost.
- Null updates to required category/product/variant/price-level fields are
  rejected during request validation rather than causing database errors.
  Nullable fields such as parent category and inherited cost remain supported.
- Standard-product stock transfers carry FEFO batch codes, expiry dates and lot
  quantities into the destination using the existing pair of stock movements.
  Quantity is conserved. Conflicting destination expiry or an unassigned source
  into an already tracked destination fails atomically. This does not infer
  historical batch links or introduce another stock-deduction engine.
- Selected-lot physical counts support parent and variant batches, increases,
  decreases and zero counts. They reuse InventoryService stock-take arithmetic,
  the existing stock ledger, batch attribution, protected operation receipts and
  audit logging. Parent balances are not overwritten by variant counts.
- New transfers may opt into request-identity retry protection. PostgreSQL
  transaction locks serialize that identity; the protected append-only audit
  ledger stores the payload hash and original movement IDs in the same commit.
  Same-identity changed payloads return 409. Product locks use stable ordering.
- POS and Backoffice preserve new transfer requests through timeout/reload and
  retry the exact original payload. Neither enables retries merely because a
  payload contains an ID: the server must advertise `audit-v1` before initial
  submission, and support is checked again before retry. Old pending requests
  are retained for original-reference reconciliation, never silently converted
  into new requests. Malformed recovery records are retained and fail closed.
- Transfer responses redact unit costs for staff without cost-view permission;
  stored movement costs remain intact. Source-branch authorization is retained.
- Product export failures now display an error rather than escaping as an
  unhandled promise rejection. The approved theme and existing navigation remain.

## API and database impact

- Existing category, product, variant and price-level APIs remain authoritative.
- `POST /api/inventory/transfers`: optional `request_id` UUID, original callers
  remain supported. Legacy calls without it do not acquire retry guarantees.
- `GET /api/inventory/transfers/capabilities`: authenticated, transfer-permission
  gated capability discovery; returns `idempotency: audit-v1`.
- `POST /api/operations/batches/stock`: adds `operation: count`; quantity is the
  actual selected-lot count in base units. Zero is permitted only for counts;
  receiving, supplier return and disposal still require positive quantities.
  Counts require both batch-management and stock-count permission.
- Required-field null updates now return validation errors. Restricted explicit
  cost writes return 403; restricted legacy null costs are omitted safely.
- **No new migration, table or column.** Development head stays
  `p7j_variant_batches`. Existing Phase 7A–7J migrations are still pending on the
  p5h production baseline. They have not been applied to production here.
- Deploy the reviewed backend before the matching frontend. Capability checks
  prevent unsafe retry against a legacy/rolled-back backend; this is not a
  substitute for a coordinated release review.

## Verification and evidence

Final machine-readable results, raw logs, synthetic screenshots and checksums
are preserved under `artifacts/phase7-final-development-20261020/` in the main
repository. Test harness output initially lives under this development
worktree's `artifacts/phase7-final-development/`.

- Complete backend regression suite: **391 passed, 146 subtests passed, zero
  failures/skips, six existing warnings**, on the existing allowlisted disposable
  PostgreSQL databases; no prepare/reset/create-database command was run.
- Seventeen new backend tests cover catalog CRUD and hierarchy/dependencies,
  company isolation, variant metadata/stock preservation, price levels, batch
  transfer conservation/rollback, selected-lot/variant/zero counts and retries,
  restricted cost preservation, required-field validation, transfer retry/hash
  conflict, actual cross-connection advisory locking and route permissions.
- Forty browser checks exercise actual POS/Backoffice components with synthetic
  adapters: catalog actions, Archive, denial states, transfer timeout/restart and
  old-server behavior, batch-count restart/retry, category dependency errors,
  and 320/390/820/1440 px layouts. External requests are blocked.
- All **24 existing POS/Backoffice test, lint and production-mode build commands
  passed**. Build verification uses the existing public staging
  entitlement keyring, not private signing material; these are development
  verification builds, not approved production publication artifacts.
- Existing backend sales, refunds, composites, variant deductions, pricing,
  currencies, employee/manager permissions, shifts, tips, restaurant/KDS/KOT,
  printing, pharmacy returns and valuation regressions remain enabled.
- The Phase 7G Build 7 APK was not modified; SHA-256 remains
  `5c05b629a822e45951cdbc1fcc3846de03030a97cfeb8b0513c3a476d26ce06b`.

Earlier browser attempts exposed test-selector mismatches for compound labels;
selectors were corrected and the entire suite rerun. An earlier failure PNG is
retained as diagnostic evidence, not presented as an approved final preview.

## Genuine remaining limitations and release gates

1. The previous inventory of 778 legacy controls/templates is not exhaustively
   accepted end-to-end. These new action checks do not relabel that whole matrix
   PASS. Browser adapters plus real PostgreSQL service/route tests are not a
   complete authenticated UI journey for every role/branch/device permutation.
2. Variant-specific interbranch transfer selection and broader variant stock-take
   screens remain incomplete. This change completes standard-product lot
   propagation and selected-lot variant counting, not every inventory workflow.
3. Offline restaurant support remains cashier-bound unpaid draft/edit recovery.
   Offline payment, KOT dispatch, advanced merge/forced-conflict workflows and
   cold-start new drafts without current authorization are not claimed complete.
4. Supplier-credit documents, automatic disposal-expense posting, tip gateway/
   payroll automation and legal/accountant tip-policy acceptance remain outside
   the implemented manual accounting workflows.
5. Real Android/WebView restart/login/offline/camera/scanner acceptance and
   Bluetooth/USB/LAN/kitchen printer output, margins, cutters and failure recovery
   remain **PENDING**. No physical hardware PASS or new APK is claimed.
6. Fresh production-clone migration/ACL rehearsal, current verified backup,
   old-client compatibility, production entitlement build inputs and reviewed
   forward recovery remain release gates. None was changed or certified by
   accessing production during this development task.

**Status: verified incremental software fixes; Phase 7 remains PARTIAL / NO-GO
for production deployment.** No deployment or APK preparation is authorized by
this report. Subscriptions/Billing and ZIMRA Fiscalisation have not been started;
they remain subsequent milestones, not replacements for unfinished acceptance.
