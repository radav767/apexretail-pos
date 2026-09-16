# Phase 4B device lifecycle contract

## Authorization and tenancy

All device-management reads and writes require the elevated `manage_devices`
permission. Owner and administrator roles receive it by default; manager and
cashier roles do not. Every location lookup is constrained by the authenticated
actor's `company_id`; a branch must be active, undeleted, in that company, and
belong to the submitted shop.

## API

- `GET /api/devices/branches/{company_id}` lists eligible company branches.
- `POST /api/devices/branches` creates an active branch in a company-owned shop.
- `PATCH /api/devices/{company_id}/{device_id}` changes non-location terminal
  configuration.
- `POST /api/devices/{company_id}/{device_id}/reassign` changes the assignment
  after explicit offline-queue and active-checkout confirmations. It locks the
  device, validates an optimistic `assignment_revision`, revokes sessions,
  increments the revision, and writes `terminal_reassign`.
- `POST /api/devices/{company_id}/{device_id}/decommission` is the separate
  dependency-recovery path. It revokes sessions and activation credentials and
  disables the terminal without deleting its identity.
- `GET /api/devices/{company_id}/{device_id}/deletion-impact` returns exact
  server-known blockers, historical sale count, pending activation state, and
  the offline-queue policy.
- `DELETE /api/devices/{company_id}/{device_id}` requires the exact displayed
  terminal name and current user password or employee PIN. It returns the same
  successful result when the tombstone already exists.

## Permanent deletion

Delete physically removes the `devices` row; it is not archive. In one database
transaction it revokes all POS sessions, removes fingerprint lockout state,
invalidates the activation credential by removing the device, inserts an
immutable `device_tombstones` deny-list/audit row, writes a `terminal_delete`
audit event, and deletes the device. The tombstone stores only keyed hashes of
the former device key/fingerprint, never reusable credentials.

Historical sales, sale items, receipts, payments encoded by the sale, refunds,
inventory movements and settlement/subscription evidence are not deleted.
Sales keep their POS/shop/branch snapshots; their nullable `device_id` becomes
null. Audit details and the tombstone retain the terminal ID, name, previous
branch, actor, timestamp and action.

An active POS session is a hard deletion dependency and produces HTTP 409 with
its exact count. Decommission is a separate action: it marks access inactive,
revokes sessions and pending activation credentials, and records an audit event.
After decommission, permanent deletion remains an explicit second operation.

## Offline and concurrency semantics

The server cannot observe transactions that exist only in a client queue. The
impact response and destructive UI therefore state that such transactions must
be synchronized before decommission/delete. Once deleted, even an idempotent
retry is rejected because device authorization runs before sale-id lookup.

Sales lock the active device row and require the submitted branch to equal the
current assignment. New clients may also submit `assignment_revision`; a stale
revision is rejected. Reassignment and deletion lock the same row, so a
concurrent synchronized sale either commits wholly before the lifecycle change
or is rejected afterward. Existing same-device session resumption and explicit
different-device takeover behavior are unchanged.

The API returns a machine-readable `code` only when it has proof of terminal
authority loss: `terminal_identity_revoked`, `terminal_assignment_changed`, or
`terminal_decommissioned`. The Android queue quarantines only those codes.
Network failures, timeouts, server errors, token expiry, ordinary 401/403
responses, and temporary authentication failures remain retryable.

A quarantined row retains the original JSON payload and `client_sale_id`, the
attempt count, human-readable error, HTTP status, server response, and timestamp
inside SQLite. Relaunch recovery resets only interrupted `syncing` rows; it does
not release quarantined rows. Automatic synchronization never selects them.
The POS displays each quarantined sale and provides a JSON recovery export that
does not modify or delete the queue. The stable `client_sale_id` remains the
server idempotency key if an operator later reconciles the exported evidence.

## Database migration

Revision `p4b_device_lifecycle`, parent `p4a_sales_inventory`, adds
`devices.assignment_revision INTEGER NOT NULL DEFAULT 1` and the additive
`device_tombstones` table. Downgrade removes only those Phase 4B structures.
