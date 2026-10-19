# Phase 7B — Employees, roles and permissions

Development branch: `phase7b/advanced-employees-permissions`.
Base: `917961fa499ba45057aeaf5fdf4bb6c27183211f` (completed Phase 7A.1).
Production, production migrations, APKs and offline queues were not modified.

## Implementation

- Employee administration: create/edit, deactivate/reactivate, search, contact/profile fields, hashed four-digit PIN replacement, branch assignment, register restrictions and employee activity filtering.
- Nine built-in roles: owner, administrator, branch manager, supervisor, cashier, inventory clerk, accountant, waiter and kitchen staff. The legacy `manager` role remains compatible. Company owners can create and edit custom roles and permission overrides.
- A canonical catalog of 34 granular permissions. Backend gates distinguish product/category/variant/composite mutations, inventory receiving/adjustment/count/transfer, shifts, reports, employee administration and role administration. Legacy permission aliases remain available to existing clients.
- Custom role changes are resolved from current database records. Deactivated employees and removed register access invalidate online POS sessions. Administrators cannot delegate permissions they do not hold; reserved owner/administrator roles cannot be assigned by ordinary employee administrators.
- Manager authorizations last 120 seconds, store only token hashes, and bind the requester, register, action and transaction context. They require another active authorized manager who has both approval authority and permission for the requested action. The manager's authority is rechecked at consumption. PIN attempts are rate limited using serialized, protected audit evidence.
- POS approval dialogs are connected to discounts, refunds, stock adjustments and cash movements. The backend also accepts action-bound price override authorization. No new arbitrary-price editor or destructive transaction-void mechanism was introduced.
- Cashier logout captures the departing cashier's token before storage is cleared. A delayed rejection for that logout cannot clear the next cashier's session; normal rejected sessions still fail closed. This is tested in Chromium using synthetic credentials.
- Sale idempotency is checked before consuming one-use discount approvals. Cash-movement retries retain their transaction identity. Manager-approved sales require an online completion; approval credentials are not persisted in offline queues.
- Employee, permission, login/logout, standard product changes, inventory adjustments, discounts, overrides, refunds and shift operations retain audit evidence. An append-only trigger prevents direct audit updates/deletions. PostgreSQL's nested foreign-key nulling on authorized terminal deletion is narrowly allowed without changing audit content.
- Restricted product/component costs are redacted from read and mutation responses; movement costs and branch inventory views respect access boundaries. Stored cost and financial records are unchanged by redaction.
- Backoffice has compact Employees, Roles, Permissions, Activity Logs and Branch Assignments pages, with browser Back support. The approved dark-green theme is retained. Device selectors expose names/IDs without activation credentials.

## API and client compatibility

New endpoints include `/employees/permissions/catalog`, `/employees/roles`, `/employees/roles/{company_id}`, `/employees/devices/{company_id}`, `/employees/activity/{company_id}`, `/employees/manager-authorizations` and `/employees/session/logout`.

Employee payloads add optional role and device restriction fields. Restricted financial actions add optional authorization tokens. Existing sales/payment arithmetic, stock movement mechanisms, receipts, tax calculations and queue formats are retained.

Security behavior intentionally tightened: sales, refunds and sales-history HTTP routes now require authentication; the old anonymous legacy sale route is rejected with HTTP 401. Existing POS clients attach the existing bearer credentials through their API client. Legacy JWTs without a device-bound session cannot bypass a newly configured device restriction. Any external anonymous API consumer must be reviewed before release.

Restricted cost response fields may now be `null` rather than disclose a value. Aggregate reports that contain profit require profit permission. Branch staff use branch-scoped inventory/report routes rather than unrestricted company-wide summaries.

The POS dashboard summary is scoped to the employee's branch. Company-wide Backoffice analytics remain limited to business users and owner/administrator employees; branch staff use the scoped summary and financial reports.

## Migration

Chain:

```text
p5h_runtime_write_permissions
  -> p7a_product_composites
  -> p7b_variant_pricing_tax
  -> p7c_employee_roles_permissions
```

`p7c` adds `employee_roles`, `employee_device_access`, `manager_authorizations`, and employee `role_id`, `role_overrides` and `device_restricted` columns. Existing employees retain their original role/permission records, with no assigned custom role and no device restriction by default. No historical sale/shift associations are generated.

New tables receive application DML privileges. No schema CREATE privilege or table ownership change is introduced. The audit trigger protects events independently of existing table-level DML grants.

The complete Alembic chain was applied to fresh disposable databases. The p7b→p7c upgrade, p7c→p7b downgrade and forward recovery were rehearsed against `apexretail_phase7b_test`. Counts and SHA-256 content hashes matched across all 40 pre-existing tables. Nonempty synthetic fixtures covered companies, shops, branches, employees, categories, products, inventory, sales, refunds and settings. Other historical tables in this particular migration fixture were empty; functional financial integration tests separately exercise settlements, expenses, currencies, cash movements and shifts.

Synthetic totals were unchanged: sale amounts `1105.00`, line costs `63.00`, stock quantity `113.000`, zero historical shift links, and zero companies with mandatory shift enforcement enabled. This evidence concerns isolated synthetic databases, not a fresh production clone.

Downgrade removes new role/approval configuration and must not be used after real Phase 7B administration without a reviewed recovery plan. All migration execution in this task was limited to disposable database names.

## Verification and artifacts

Persistent review artifacts: `/root/apexretail-pos/artifacts/phase7b-20261019/`.

- `backend-regression.log`: full backend run, including all configured PostgreSQL integration suites; final counts are recorded in the log.
- `frontend-test-results.json`: 22 successful commands (12 POS test commands, six Backoffice test commands, both linters and both production builds).
- `migration-rehearsal.json`: upgrade/downgrade/forward recovery, historical row counts, totals and per-table content hashes.
- `responsive-checks.json`: 24 page/layout checks across desktop, tablet, 390px Android and 320px narrow viewports; browser Back tested on all four; manager approval tested at three widths.
- `index.html` and 16 PNGs: actual React development screens using synthetic adapters; external HTTPS requests were blocked during capture.
- `builds-final/pos/` and `builds-final/backoffice/`: saved frontend review builds. The POS build used the existing public entitlement keyring (`prod-2026-10-13-r1`); no signing key was created or changed.
- `changed-files.txt`, `SHA256SUMS` and `release.json`: source/file and build evidence for the local implementation commit.

Final backend result: **268 passed, 104 subtests passed, zero failed, zero skipped**, with four existing deprecation warnings. All 22 frontend commands pass. Browser checks also verify the departing cashier's logout identity, protection of the next cashier's session, and normal revocation handling.

Warnings: four existing backend deprecation warnings (Pydantic class-based configuration and Starlette/httpx); existing frontend hook/preview warnings; POS main chunk exceeds Vite's 500kB advisory. Linters and builds exit successfully. No warnings were suppressed.

## Approval requirements and limitations

- Review the new employee/role pages and permissions on real business scenarios before deployment.
- Rehearse the pending migration chain on a fresh protected production clone and compare current financial/inventory evidence before authorizing deployment. The synthetic rehearsal does not replace this release gate.
- Online revocations take effect immediately. A disconnected terminal cannot learn a new revocation until reconnection; existing bounded offline authorization rules remain in force. New manager approvals and restricted manager-approved sales require connectivity.
- Price override approval is supported in the backend, but this change does not introduce a new POS price editor. Cancellations continue using existing safe refund/cancellation workflows.
- Browser viewport tests are automated Chromium checks. Physical Android/WebView, printer, scanner and real-user acceptance remain manual. The APK was neither rebuilt nor installed.
- Publish migration/backend/POS/Backoffice only in a separately approved coordinated release after backup and recovery review. Keep mandatory shift enforcement disabled. No production deployment was performed.
