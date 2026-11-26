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
    if method=='POST' and path.endswith('/ready') and domain=='printing':
        replay='Current actor/epoch/register/station and original sending claim nonce; read-only authorization before transport, no attempt or delivery result mutation'
        gap='physical_printer_and_installed_device_acceptance_pending'
    if method=='POST' and path.endswith('/quotation-pricing'):
        sources+=';business_operations/saved_pricing.py'
        policy='test_only_saved_quotation_plan'
        replay='Current identity/epoch/register and full UUID/payload proof before original saved result; new plans require licensed current draft and explicit test mode; no stock/payment effect'
    if method=='GET' and path=='/api/operations/orders':
        replay='Current tenant/branch/role/epoch historical read; limit1–100, offset0–100000, deterministic created/id order. No stock/payment or subscription mutation. Actor-scoped retained requests recover by authorized original-ID reads independently of page membership; no automatic replay.'
        gap='bounded_old_pages_and_first_party_retained_discovery_verified_offset_pages_not_a_snapshot_under_inserts'
    exact = method == 'POST' and (
        path in {'/api/customers/checkout', '/api/sales', '/api/sales/refunds', '/api/expenses', '/api/credit/settlements', '/api/inventory/stock-take',
                 '/api/inventory/transfers', '/api/operations/orders', '/api/operations/offline/drafts',
                 '/api/operations/offline/edits', '/api/operations/offline/kitchen', '/api/operations/offline/kds',
                 '/api/operations/batches/stock', '/api/operations/batches/returns/inspect', '/api/operations/tips/entries',
                 '/api/shifts/open', '/api/shifts/current/cash-movements', '/api/shifts/offline-resolutions'}
        or path.startswith('/api/operations/orders/') and path.endswith(('/settle','/quotation-transition','/quotation-revision','/quotation-pricing'))
        or domain == 'shifts' and path.endswith(('/cash-movements','/close','/manager-close')))
    if exact:
        observed = 'transaction_service_replay_policy'
        gap = 'transaction_policy_implemented_evidence_scope_in_progress_report_full_acceptance_pending'
        replay = ('Current actor/scope/register and complete durable payload proof before committed result; '
                  'current server license/modules for pending/new commands. Legacy incomplete proofs conflict; '
                  'optional legacy command IDs have no deduplication guarantee. No stock/payment re-execution.')
        if domain == 'inventory': sources += ';inventory/command_policy.py;inventory/count_requests.py;inventory/transfer_repository.py'
        if path.endswith('/quotation-transition'):
            gap = 'immutable_validity_terms_and_action_proof_accepted_conversion_stock_races_verified'
            replay = 'Current actor/register/revision plus exact immutable action proof; new workflow needs wholesale license. Freeze validity/zero-discount/tax/pricing; no stock/payment until accepted current-stock conversion, with atomic final sale comparison.'
            sources += ';business_operations/quotations.py'
        if path.endswith('/quotation-revision'):
            gap = 'immutable_parent_child_revision_lineage_one_conversion_and_races_verified_device_acceptance_pending'
            replay = 'Full original request/actor/register proof recovers same linked draft after expiry; root lock before order/checkout, current license for new revision, immutable original terms/lineage, later sent supersession and one converted sale per lineage.'
            sources += ';business_operations/quotation_revisions.py'
        if path == '/api/customers/checkout':
            gap = 'identified_basic_contact_creation_no_credit_stock_payment_effects_verified'
            replay = 'Current actor/tenant/customers_view plus immutable UUID/full-input proof; exact recovery survives expiry. New basic contact creation needs license and cannot accept credit/status/price-tier fields.'
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
    if path.endswith('/pricing/review'):
        policy = 'read_only_proposed_pricing_review'
        replay = 'Current quotation version/tenant/branch/role and discount permissions, configured units/prices/rates only. Bounded integer/Fraction discount/tax/currency proposal; no accepted terms, stock, sale, payment, provider or command mutation. Posting remains disabled.'
        sources += ';business_operations/pricing_review.py;accounting/planning.py'
        gap = 'proposal_arithmetic_verified_discount_unit_currency_checkout_enablement_pending'
    if '/reports/credit-reconciliation/' in path:
        sources += ';reports/credit_reconciliation.py'
        gap = 'single_statement_current_receivable_ledger_proof_scoped_no_repair_no_historical_asof_claim'
    if domain == 'employees' and method in {'PATCH', 'DELETE'}:
        observed = 'service_security_exception_policy'
        gap = 'security_reduction_epoch_and_direct_tenant_checks_verified_full_role_ui_acceptance_pending'
    if domain == 'subscriptions' and method == 'GET':
        sources += ';subscriptions/offline_actor.py'
        gap = 'fresh_nonce_signed_current_opaque_actor_register_actions_bounded_browser_lease_verified_installed_device_acceptance_pending'
    if path.endswith('/employees/session/logout'):
        gap = 'legacy_user_employee_jwt_opaque_revocation_and_pin_races_verified_device_acceptance_pending'
    if path.startswith('/api/inventory/workflows'):
        sources = 'workflows/core.py;workflows/procurement.py;workflows/counts.py;workflows/documents.py;workflows/media.py;workflows/outputs.py;workflows/delivery.py;workflows/recovery.py;inventory/service.py'
        observed = 'workflow_service_command_policy'
        gap = 'real_panel_api_persistence_races_rollback_media_pdf_qr_sink_subset_verified_full_shell_device_provider_finance_acceptance_pending'
        if read:
            policy = 'scoped_workflow_evidence_read'
            replay = 'Current tenant/branch/role and source document permissions; purchasing costs require existing cost visibility. Bounded records/history; no stock/payment effect.'
        elif '/commands/' in path and path.endswith('/cancel'):
            policy = 'workflow_original_recovery_or_cancellation_fence'
            replay = 'Serialize original UUID; recover committed full-input/actor/register proof with current permission, or permanently fence that actor/company uncommitted UUID before replacement. Survives expiry; no stock/payment replay.'
        elif path.endswith('/documents'):
            policy = 'immutable_historical_document_render'
            replay = 'Full UUID/input/actor/register proof; immutable escaped source/template snapshot permitted after expiry with current source permissions. No new sale/payment/stock/print/fiscal/provider action.'
        elif '/retention/' in path:
            policy = 'retained_evidence_selection_policy'
            replay = 'Current owner/settings/tenant/branch; immutable original assets/documents/outputs remain untouched. Archive/replay allowed after expiry, reactivation licensed. Same normalized branch asset reuses identity; archive does not reclaim quota or delete evidence.'
        elif '/outputs' in path:
            policy = 'immutable_historical_output_or_authenticated_lookup'
            replay = 'Current source/tenant/branch/cost authority. Identified PDF/authenticated-lookup QR coalesce by original document/format; immutable stored bytes and full actor/register command proof. Lookup requires authentication and exact digest. No public/payment/fiscal QR or stock/payment/provider effect.'
        elif '/delivery/' in path:
            policy = 'consent_bound_test_only_sink'
            replay = 'Current owner/settings/source authority; immutable request proof; original queue actor/session/register and granted consent rechecked under locks before new licensed capture. Consent revoke/cancel and captured recovery survive expiry. Explicit APP_ENV=test/encryption key/synthetic recipients only, encrypted sink captured status never provider delivery. Distinct enqueue/capture IDs coalesce; no transport exists.'
        elif path.endswith('/media'):
            policy = 'licensed_private_normalized_media'
            replay = 'Current owner/settings/tenant/branch and license before bounded decode/metadata-free raster archive. Full input/actor/register UUID replay; immutable assets and serialized tenant quota, no public URL/file access or official branding.'
        else:
            policy = 'workflow_exact_command_or_licensed_write'
            replay = 'Current actor epoch/tenant/branch/role/register before full immutable UUID/input replay; current license/modules for new work. Draft/approval has no movement. Receipt/return/count stock and parent/child evidence commit once atomically; cutoff changes require explicit recount.'
    if path == '/api/sales/v2/split':
        policy = 'synthetic_versioned_atomic_split_checkout'
        observed = 'transaction_service_replay_policy'
        sources += ';sales/split.py;sales/split_schema.py;accounting/planning.py'
        replay = 'Current actor/epoch/tenant/branch/register/revision and full original sale/tender input proof recover committed legs before current price/license/test-mode checks. New cash/credit work requires current license and explicit APP_ENV=test/SPLIT_CHECKOUT_MODE=test. One atomic sale/stock/debt/leg/proof commit; no offline/provider authority.'
        gap = 'synthetic_cash_credit_and_fx_checkout_refund_rollback_races_verified_receipt_report_ui_provider_acceptance_pending_default_disabled'
    if path == '/api/sales/v2/split/refunds':
        policy = 'synthetic_versioned_original_tender_refund'
        observed = 'transaction_service_replay_policy'
        sources += ';sales/split_refunds.py;sales/split_schema.py;sales/refund_accounting.py;accounting/planning.py'
        replay = 'Current actor/epoch/tenant/branch/register/revision plus exact original item/allocation input recover immutable receipt/legs before current license/test-mode checks. New test-only refunds lock original sale and receivable, verify collection/note proof, reduce unpaid debt first, cap original cash/currency budgets, atomically restore stock and persist credit note/allocations/native proof. Collected-credit excess and method overrides reject before effects.'
        gap = 'synthetic_partial_final_fx_tax_collection_contention_and_rollback_verified_paid_credit_payout_receipt_report_ui_provider_acceptance_pending'
    if path.startswith('/api/sales/v2/split/history/'):
        sources += ';sales/split_history.py'
        replay = 'Historical original tender/refund/current debt disclosure after current identity/revocation and native receipt permissions for selected and original branches. One SQL snapshot, independent ledger aggregates, bounded authorized-branch history page; no reprint, price/license/mode dependency, posting or immutable document rewrite.'
        gap = 'single_snapshot_original_budget_and_branch_pagination_verified_dated_cashflow_shift_receipt_ui_parity_pending'
    if path.startswith('/api/reports/tender-flows/'):
        sources += ';accounting/tender_flows.py;shifts/split_accounting.py'
        replay = 'Current identity/revocation/revenue and collection permissions plus own event tenant/branch/shift. Aware UTC half-open <=366day window; one statement independently aggregates original/refund revenue, applied payments, debt and original cash units with frozen FX residuals. Exact committed commands contribute once. Historical read survives expiry; no provider/posting authority or current-rate reconstruction.'
        gap = 'synthetic_dates_boundaries_fx_replay_and_shift_close_lock_orders_verified_receipt_ui_full_device_acceptance_pending'
    if path == '/api/products/{company_id}/selection':
        sources += ';products/selection.py;products/access.py;workflows/core.py'
        replay = 'Direct current identity/epoch/tenant/branch/register plus existing catalogue permission for general purpose or business-settings authority for charge purpose. Bounded server search/pages and exact selected-ID lookup; charge count/rows require active undeleted explicit nontracking service/non_stock products. Cost redaction, literal wildcards, expired configuration reads and selection-contract capability retained; no mutation or recipe authority.'
        gap = 'synthetic_scopes_purpose_pages_selected_id_and_current_guard_verified_profile_shell_acceptance_and_advanced_management_filters_separate'
    if path == '/api/operations/profile' and method == 'PUT':
        sources += ';business_operations/service.py;workflows/core.py'
        replay = 'Current direct actor/epoch/register and business-settings permission/write license; product eligibility refreshed and share-locked in deterministic ID order through commit. Unversioned configuration PUT, not an immutable UUID command/recovery or financial transaction. Optional clear retains profile policy; future catalogue changes require renewed eligibility.'
        gap = 'synthetic_stale_identity_map_and_both_catalog_lock_orders_verified_unversioned_profile_configuration_limit_explicit'
    if path.startswith('/api/settings/preferences/'):
        sources += ';business_settings/preferences.py;workflows/core.py'
        policy = 'scoped_presentation_read_or_exact_command'
        replay = 'Current epoch/tenant/authorized branch/register; company defaults require owner/admin for writes. Versioned company-branch-device selector/shared-tool appearance only, device assignment revision bound. Explicit v2 saves retain immutable v1 fingerprints/results; legacy writes preserve newer colour overrides. New saves require business-settings permission/license; immutable exact UUID/body/actor/register acknowledgement recovery precedes license. Scope lock and expected version fence competing writes; no stock/payment/terminal authority.'
        gap = 'synthetic_inheritance_clear_role_expiry_rollback_and_independent_equal_stale_assignment_races_verified_bounded_shared_tool_light_dark_system_verified_full_workspace_theme_and_canonical_ten_section_taxonomy_pending'
    if path.startswith('/api/reports/reconciliation/'):
        sources += ';accounting/exports.py;accounting/tender_flows.py'
        replay = 'Read-only current identity/epoch/revenue+credit authority and own event tenant/branch/shift; second revocation check before bytes. One statement snapshot; bounded internal CSV pages and lossless JSON preserve receipt revenue/tax independently from payments/debt/change/FX. Typed numeric columns and formula-neutralised text; no posting/provider/vendor integration or historical output mutation.'
        gap = 'synthetic_API_ledger_pages_limits_scopes_and_independent_reader_writer_revocation_verified_hardware_provider_AT_cross_browser_pending'
    if path.startswith('/api/sales/receipt/'):
        sources += ';sales/split_receipts.py'
        replay = 'Native historical receipt/reprint scope; split original/refund disclosure additionally requires current direct-service actor/epoch/register context. Immutable original allocation/currency/change rows; no current debt/rate substitution, financial posting or provider confirmation. Reprint metadata is separate from original amounts.'
        gap = 'split_api_print_queue_58_80_and_a4_software_disclosure_verified_whole_shell_hardware_acceptance_pending'
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
