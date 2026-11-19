"""Attach explicit observed service/replay policy to every registered operation.

Coverage is exhaustive; this assessment is not an enforcement certification.
Run in the same unreachable environment as phase11_endpoint_inventory.py.
"""
import csv
import io
import subprocess
import sys
from pathlib import Path


DOMAINS = {
    'auth': ('Business authentication, revocation and recovery', 'auth/service.py;auth/dependencies.py;auth/sessions.py;auth/remembered.py;auth/recovery.py;auth/handoff.py'),
    'products': ('Catalog permission, tenant and branch checks; explicit write dependencies where listed', 'products/router.py;products/service.py;products/selection.py'),
    'inventory': ('Branch/variant/batch scopes; optimistic counts; transaction-specific movement idempotency', 'inventory/router.py;inventory/service.py'),
    'branches': ('Tenant and branch management', 'inventory/branch_router.py;inventory/branch_repository.py'),
    'transfers': ('Source/destination branch authorization and movement ownership', 'inventory/transfer_router.py;inventory/transfer_repository.py'),
    'sales': ('Current tenant/branch/role/register and complete request proof before committed sale replay; current license for new work', 'sales/service.py;sales/commands.py;sales/refund_commands.py;subscriptions/write_policy.py;financial_context.py'),
    'customers': ('Tenant scope; credit/status modifications require management authority', 'customers/service.py'),
    'credit': ('Tenant/branch/permission; full request/actor/register proof for exact collections; current license for new payments', 'credit/service.py;financial_commands.py;subscriptions/write_policy.py'),
    'expenses': ('Tenant/branch, expense permission and posted-record identity', 'expenses/service.py;financial_commands.py;subscriptions/write_policy.py'),
    'currencies': ('Tenant and currency-management roles; immutable rates and quote versions', 'currencies/service.py'),
    'devices': ('Register identity, activation, tombstones, tenant/reassignment authority', 'devices/service.py;devices/authority.py'),
    'employees': ('Current permissions/device restrictions; legacy JWT and opaque epoch revocation; same-business revocation-only POS logout', 'employees/service.py;employees/admin_service.py;employees/revocation.py;employees/logout.py;auth/dependencies.py'),
    'settings': ('Company management permissions; receipt/shop preferences', 'business_settings/router.py;business_settings/service.py'),
    'shifts': ('Current cashier/register/epoch and full shift command proof; licensed opens/drawer writes; evidence-only close/quarantine exceptions', 'shifts/service.py;shifts/commands.py;financial_context.py'),
    'printing': ('Tenant/branch/register/station access; original sale and queue identity preserved', 'printing/service.py'),
    'operations': ('Transaction-service current write/module policy; durable actor/payload/context proofs for committed replay', 'business_operations/router.py;business_operations/service.py;business_operations/offline.py;business_operations/batch_stock.py;business_operations/returns.py;business_operations/tips.py'),
    'fiscal': ('Owner-only preparation/configuration; tenant/branch sale-status reads; no commissioned connector', 'fiscal/router.py;fiscal/service.py'),
    'reports': ('Historical financial reads retain current tenant/branch/role permissions after expiry/module changes', 'reports/router.py;subscriptions/feature_guard.py'),
    'dashboard': ('Tenant, revenue/profit roles and branch filtering', 'dashboard/router.py'),
    'subscriptions': ('Business owner/tenant subscription visibility and provider signature/renewal policy', 'subscriptions/router.py;subscriptions/service.py'),
    'platform': ('Separate platform sessions, MFA and platform role permits; no business-token substitution', 'subscriptions/platform_router.py;subscriptions/platform_auth.py;subscriptions/platform_mfa.py'),
    'billing': ('Commercial owner/platform policy; invoice/payment identity and confirmed renewal', 'subscriptions/platform_router.py;subscriptions/commercial.py'),
}


def assess(row):
    path, method = row['path'], row['method']
    domain = path.split('/')[2] if path.startswith('/api/') else 'health'
    if domain == 'health':
        return ('health', 'public_health', 'No business mutation', 'No replay mutation', 'main.py', 'not_applicable')
    if domain not in DOMAINS:
        raise RuntimeError('Unreviewed endpoint namespace: ' + domain)
    description, sources = DOMAINS[domain]
    read = method in {'GET', 'HEAD', 'OPTIONS'}
    if domain == 'platform':
        policy = 'platform_mfa_role'
        replay = 'Platform action-specific authority and state checks; no tenant subscription gate'
    elif domain == 'auth' or domain == 'employees' and any(x in path for x in ('pin-login', 'session/logout')):
        policy = 'authentication_recovery'
        replay = 'No sales/stock mutation; authentication, one-use or revocation semantics apply'
    elif domain in {'subscriptions', 'billing'}:
        policy = 'subscription_recovery_or_provider'
        replay = 'Renewal requires confirmed provider/signature/idempotency; never fabricate success'
    elif read:
        policy = 'historical_or_configuration_read'
        replay = 'Read existing records; preserve tenant/branch/role and original fiscal/receipt identity'
    elif domain == 'fiscal' or domain == 'printing':
        policy = 'existing_document_or_delivery'
        replay = 'Reuse original sale/document/job; retries must not create sales, deduct stock or submit a new fiscal transaction'
    elif '/recover' in path or path.endswith('/review'):
        policy = 'committed_command_recovery'
        replay = 'Read/acknowledge exact original command identity; no new stock/payment movement'
    elif domain == 'shifts' and method == 'POST' and path.endswith(('/close', '/manager-close')):
        policy = 'shift_evidence_finalization'
        replay = 'Expired-account closure allowed with current scope/permission and complete original closing proof; no new drawer/payment/stock effect'
    elif domain == 'shifts' and path.endswith('/offline-resolutions'):
        policy = 'quarantine_evidence_or_new_sale_resolution'
        replay = 'Retaining quarantine is evidence-only; posting requires current write license. Full resolver/action/reason/payload proof and original signed shift identity required'
    elif domain == 'employees' and method in {'PATCH', 'DELETE'}:
        policy = 'employee_security_reduction_or_licensed_configuration'
        replay = 'Current employees_manage authority required. Security-only PIN resets, disabling/deleting and rights/device reductions survive expiry; grants/reactivation/ordinary changes require current license. Changed employee/shared-role security atomically revokes epochs and opaque sessions; no general mutation idempotency contract.'
    elif domain == 'devices' and any(x in path for x in ('heartbeat', 'decommission')):
        policy = 'device_security_or_health'
        replay = 'Identity/status validation; decommission must remain possible without subscription renewal'
    else:
        policy = 'new_business_write'
        replay = 'Current write license required for new mutation; exact committed replay should return original result only after actor/scope/payload validation'
    observed = 'explicit_billable_dependency' if row['billable_dependency'] else 'operational_write_dependency' if 'require_operational_writes' in row['dependencies'] else 'service_or_exception_policy'
    # Be explicit about the remaining behavioral gaps instead of conflating a
    # route matrix with proof that each direct service/replay path is protected.
    gap = 'none_identified_in_dependency_scope'
    if policy == 'new_business_write':
        gap = 'service_direct_call_and_exact_replay_acceptance_pending'
        if observed == 'service_or_exception_policy': gap = 'write_license_gap_requires_transaction_specific_guard'
    exact = method == 'POST' and (
        path in {'/api/sales', '/api/sales/refunds', '/api/expenses', '/api/credit/settlements', '/api/inventory/stock-take',
                 '/api/inventory/transfers', '/api/operations/orders', '/api/operations/offline/drafts',
                 '/api/operations/offline/edits', '/api/operations/offline/kitchen', '/api/operations/offline/kds',
                 '/api/operations/batches/stock', '/api/operations/batches/returns/inspect', '/api/operations/tips/entries',
                 '/api/shifts/open', '/api/shifts/current/cash-movements', '/api/shifts/offline-resolutions'}
        or path.startswith('/api/operations/orders/') and path.endswith('/settle')
        or domain == 'shifts' and path.endswith(('/cash-movements','/close','/manager-close')))
    if exact:
        observed = 'transaction_service_replay_policy'
        gap = 'transaction_policy_implemented_evidence_scope_in_progress_report_full_acceptance_pending'
        replay = ('Current actor/scope/register and complete durable payload proof before committed result; '
                  'current server license/modules for pending/new commands. Legacy incomplete proofs conflict; '
                  'optional legacy command IDs have no deduplication guarantee. No stock/payment re-execution.')
        if domain == 'inventory': sources += ';inventory/command_policy.py;inventory/count_requests.py;inventory/transfer_repository.py'
        if path == '/api/sales/refunds':
            gap = 'identified_refund_replay_implemented_legacy_idless_clients_not_deduplicated'
            replay = 'Request UUID/full immutable proof returns original refund without stock/approval effects; new corrections require current license; first-party pending intents retain identity. Legacy callers without UUID retain no deduplication contract.'
        if policy == 'shift_evidence_finalization':
            replay = 'Closure freezes existing evidence after current actor/permission/register checks even when expired; exact full-request replay only, no new drawer/payment/stock effect'
        elif policy == 'quarantine_evidence_or_new_sale_resolution':
            replay = 'Current resolver/branch/signed original shift plus full review proof; expired quarantine retention allowed; new sale posting needs current license; original summaries remain frozen'
    elif policy == 'new_business_write' and domain in {'currencies', 'expenses', 'credit', 'customers', 'settings'}:
        observed = 'service_new_write_policy'
        gap = 'write_guard_subset_verified_no_general_idempotency_contract'
    elif domain == 'products' and not read:
        observed = 'service_catalog_write_policy'
        gap = 'direct_license_module_import_preflight_verified_legacy_create_key_not_full_replay_proof_direct_actor_contract_unchanged'
    elif domain == 'sales' and not read:
        gap = 'new_refund_guard_implemented_no_refund_command_idempotency_contract'
    elif domain == 'inventory' and not read:
        gap = 'direct_grn_adjustment_guard_implemented_no_legacy_command_idempotency_contract'
    elif domain == 'operations' and not read and policy != 'committed_command_recovery':
        gap = 'service_write_guard_subset_verified_remaining_operation_permission_replay_acceptance'
    if path.endswith('/selection') and domain == 'products':
        gap = 'bounded_search_branch_stock_no_cost_read_verified_browser_selector_subset_adopted'
    if path.startswith('/api/reports/financial-summary/'):
        gap = 'historical_module_exception_implemented_current_financial_scope_retained'
    if domain == 'employees' and method in {'PATCH', 'DELETE'}:
        observed = 'service_security_exception_policy'
        gap = 'security_reduction_epoch_and_direct_tenant_checks_verified_full_role_ui_acceptance_pending'
    if domain == 'subscriptions' and method == 'GET':
        sources += ';subscriptions/offline_actor.py'
        gap = 'fresh_nonce_signed_current_opaque_actor_register_actions_bounded_browser_lease_verified_installed_device_acceptance_pending'
    if path.endswith('/employees/session/logout'):
        gap = 'legacy_user_employee_jwt_opaque_revocation_and_pin_races_verified_device_acceptance_pending'
    return domain, policy, description, replay, sources, observed + ':' + gap


def main():
    script = Path(__file__).with_name('phase11_endpoint_inventory.py')
    result = subprocess.run([sys.executable, str(script)], check=True, text=True, capture_output=True)
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    fields = ['domain', 'policy', 'service_policy', 'replay_policy', 'service_sources', 'observed_and_gap']
    for row in rows:
        row.update(zip(fields, assess(row)))
        row['review'] = 'policy_assessed_acceptance_gaps_explicit'
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    print(result.stderr.strip(), file=sys.stderr)


if __name__ == '__main__': main()
