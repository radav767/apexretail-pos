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
    'auth': ('Business authentication, revocation and recovery', 'auth/service.py;auth/dependencies.py;auth/sessions.py'),
    'products': ('Catalog permission, tenant and branch checks; explicit write dependencies where listed', 'products/router.py;products/service.py'),
    'inventory': ('Branch/variant/batch scopes; optimistic counts; transaction-specific movement idempotency', 'inventory/router.py;inventory/service.py'),
    'branches': ('Tenant and branch management', 'inventory/branch_router.py;inventory/branch_repository.py'),
    'transfers': ('Source/destination branch authorization and movement ownership', 'inventory/transfer_router.py;inventory/transfer_repository.py'),
    'sales': ('Current tenant/branch/role/register checks before committed client-sale lookup', 'sales/service.py;financial_context.py'),
    'customers': ('Tenant scope; credit/status modifications require management authority', 'customers/service.py'),
    'credit': ('Tenant/branch, credit settlement authority and immutable payment identities', 'credit/service.py'),
    'expenses': ('Tenant/branch, expense permission and posted-record identity', 'expenses/service.py'),
    'currencies': ('Tenant and currency-management roles; immutable rates and quote versions', 'currencies/service.py'),
    'devices': ('Register identity, activation, tombstones, tenant/reassignment authority', 'devices/service.py;devices/authority.py'),
    'employees': ('Current employee permissions, role grant ceilings, device restrictions; PIN-session revocation', 'employees/service.py;employees/admin_service.py'),
    'settings': ('Company management permissions; receipt/shop preferences', 'business_settings/router.py;business_settings/service.py'),
    'shifts': ('Cashier/register binding, shift manager authority, immutable closes and offline resolutions', 'shifts/service.py;financial_context.py'),
    'printing': ('Tenant/branch/register/station access; original sale and queue identity preserved', 'printing/service.py'),
    'operations': ('Operational writes dependency plus restaurant/hospitality/wholesale/pharmacy feature and actor checks', 'business_operations/router.py;business_operations/service.py;business_operations/offline.py'),
    'fiscal': ('Owner-only preparation/configuration; tenant/branch sale-status reads; no commissioned connector', 'fiscal/router.py;fiscal/service.py'),
    'reports': ('Tenant/branch financial permissions; advanced_reports feature still gates financial-summary GET', 'reports/router.py;subscriptions/feature_guard.py'),
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
    if domain == 'sales' and not read:
        gap = 'early_billable_and_feature_guards_can_block_committed_replay_after_expiry_or_plan_change'
    if domain == 'operations' and not read and policy != 'committed_command_recovery':
        gap = 'early_operational_license_guard_replay_review_required'
    if path.startswith('/api/reports/financial-summary/'):
        gap = 'historical_advanced_reports_feature_exception_requires_product_policy'
    return domain, policy, description, replay, sources, observed + ':' + gap


def main():
    script = Path(__file__).with_name('phase11_endpoint_inventory.py')
    result = subprocess.run([sys.executable, str(script)], check=True, text=True, capture_output=True)
    rows = list(csv.DictReader(io.StringIO(result.stdout)))
    fields = ['domain', 'policy', 'service_policy', 'replay_policy', 'service_sources', 'observed_and_gap']
    for row in rows: row.update(zip(fields, assess(row)))
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    print(result.stderr.strip(), file=sys.stderr)


if __name__ == '__main__': main()
