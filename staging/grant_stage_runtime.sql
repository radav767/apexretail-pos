-- NEW STAGING CLUSTER ONLY: establish pre-existing application DML baseline.
-- Phase 7 migrations retain their explicit column/append-only grants.
DO $$ BEGIN
  IF current_database() <> 'apexretail_phase7f_acceptance'
     OR current_user <> 'apexstage7f'
     OR current_setting('port') <> '55437'
     OR current_setting('data_directory') <> '/tmp/apexretail-phase7f-runtime/postgres'
  THEN RAISE EXCEPTION 'Not the dedicated staging instance'; END IF;
END $$;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO apex_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO apex_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO apex_user;
GRANT INSERT ON companies,shops,branches,users,employees,devices,company_settings,
 company_subscriptions,company_subscription_history,company_currencies,currency_exchange_rates,
 employee_shop_access,pos_sessions,device_activation_attempts,device_tombstones,
 customers,credit_receivables,credit_settlements,expense_categories,expenses,
 products,categories,product_creation_requests,sales,sale_items,inventory_balances,inventory_movements,cashier_shifts,
 cashier_shift_currency_snapshots,cashier_shift_cash_movements,offline_sale_resolutions,
 subscription_checkout_sessions,subscription_webhook_events,audit_events TO apex_user;
GRANT UPDATE,DELETE ON companies,shops,branches,users,employees,devices,company_settings,
 company_subscriptions,company_currencies,employee_shop_access,pos_sessions,
 device_activation_attempts,customers,credit_receivables,expense_categories,
 products,categories,inventory_balances,subscription_checkout_sessions,subscription_webhook_events TO apex_user;
-- Never grant broad UPDATE on shifts, immutable ledgers, tips or audit history.
