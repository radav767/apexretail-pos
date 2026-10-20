"""Commercial billing/security through existing rollback-only PostgreSQL fixtures."""
import calendar
import unittest
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
import httpx
from fastapi import HTTPException
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.auth.security import hash_password,create_access_token
from app.models import CompanySubscription,CompanySubscriptionHistory,Sale,InventoryMovement
from app.models.commercial import PlatformAdmin,BillingInvoice,BillingPayment,BillingNotice,PlatformAudit,PlatformSession
from app.subscriptions.commercial_schema import PlanInput,InvoiceInput,PaymentInput,LicenseInput
from app.subscriptions.commercial import CommercialService,add_months,effective_status,enforce_capacity,enforce_feature
from app.subscriptions.platform_auth import login,authenticate,permit
from app.subscriptions.service import SubscriptionService
import test_phase7d_operations as fixtures

UTC=timezone.utc

class BillingCalendarTests(unittest.TestCase):
    def test_all_billing_periods_and_end_of_month(self):
        value=datetime(2028,1,31,tzinfo=UTC)
        for months in (1,3,6,12):
            with self.subTest(months=months):
                result=add_months(value,months)
                self.assertEqual(result.day,min(31,calendar.monthrange(result.year,result.month)[1]))
        self.assertEqual(add_months(value,1).day,29)

class CommercialTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.admin=PlatformAdmin(email=str(uuid4())+'@platform.test',password_hash=hash_password('synthetic-platform-password'),role='super_admin')
        self.db.add(self.admin);await self.db.commit()
        self.svc=CommercialService(self.db,self.admin)
        self.subscription=await SubscriptionService(self.db).get_or_create_trial(self.company.id)
    async def plan(self,**changes):
        values=dict(name='Synthetic quarterly',months=3,price='9.99',currency='EUR',features={'restaurant':True,'pharmacy':True},
            branch_limit=2,device_limit=1,employee_limit=2,offline_grace_hours=24)
        values.update(changes)
        return await self.svc.save_plan(PlanInput(**values))
    async def invoice(self,plan=None,**changes):
        plan=plan or await self.plan()
        values=dict(company_id=self.company.id,plan_id=plan.id,request_id=uuid4(),due_at=datetime.now(UTC)+timedelta(days=7),reason='Synthetic invoice')
        values.update(changes);return await self.svc.issue(InvoiceInput(**values))
    def payment(self,invoice,**changes):
        values=dict(company_id=self.company.id,invoice_id=invoice.id,request_id=uuid4(),amount=invoice.amount,method='bank',reference=str(uuid4()),reason='Verified synthetic bank receipt')
        values.update(changes);return PaymentInput(**values)
    async def test_partial_payment_and_final_activation_are_exactly_once(self):
        invoice=await self.invoice();first=self.payment(invoice,amount='4')
        await self.svc.confirm(first)
        self.assertEqual(self.subscription.status,'trial');self.assertIsNone(invoice.fulfilled_at)
        last=self.payment(invoice,amount='5.99');paid=await self.svc.confirm(last)
        expiry=self.subscription.current_period_ends_at;again=await self.svc.confirm(last)
        self.assertEqual(paid.id,again.id);self.assertEqual(self.subscription.current_period_ends_at,expiry)
        self.assertEqual(self.subscription.status,'active');self.assertEqual(self.subscription.billing_currency,'EUR')
        self.assertEqual(self.subscription.commercial_terms['branch_limit'],2)
        self.assertEqual((await self.db.execute(select(func.count(BillingPayment.id)).where(BillingPayment.company_id==self.company.id))).scalar_one(),2)
        self.assertEqual((await self.db.execute(select(func.count(CompanySubscriptionHistory.id)).where(CompanySubscriptionHistory.company_id==self.company.id,CompanySubscriptionHistory.action=='commercial_renewed'))).scalar_one(),1)
    async def test_plan_edits_cannot_rewrite_issued_invoices_or_reuse_invoice_identity(self):
        plan=await self.plan();request=InvoiceInput(company_id=self.company.id,plan_id=plan.id,request_id=uuid4(),due_at=datetime.now(UTC),reason='Synthetic immutable invoice')
        invoice=await self.svc.issue(request)
        self.assertEqual(invoice.id,(await self.svc.issue(request)).id)
        terms=PlanInput(name='Updated',months=12,price=99,currency='USD',expected_version=plan.version)
        await self.svc.save_plan(terms,plan.id)
        self.assertEqual(invoice.currency,'EUR');self.assertEqual(invoice.snapshot['months'],3)
        with self.assertRaises(HTTPException):await self.svc.issue(request.model_copy(update={'custom_amount':Decimal('1')}))
        with self.assertRaises(HTTPException):await self.svc.save_plan(terms,plan.id)
    async def test_payment_reference_and_mutated_retry_cannot_duplicate_renewals(self):
        invoice=await self.invoice();data=self.payment(invoice);await self.svc.confirm(data)
        for changed in (data.model_copy(update={'amount':Decimal('8')}),data.model_copy(update={'request_id':uuid4()})):
            with self.subTest(changed=changed.request_id),self.assertRaises(HTTPException):await self.svc.confirm(changed)
    async def test_renewal_extends_unexpired_period_and_preserves_business_financial_records(self):
        sales=(await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id==self.company.id))).scalar_one()
        moves=(await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one()
        invoice=await self.invoice();await self.svc.confirm(self.payment(invoice));end=self.subscription.current_period_ends_at
        second=await self.invoice();await self.svc.confirm(self.payment(second))
        self.assertEqual(self.subscription.current_period_started_at,end)
        self.assertEqual(self.subscription.current_period_ends_at,add_months(end,3))
        self.assertEqual((await self.db.execute(select(func.count(Sale.id)).where(Sale.company_id==self.company.id))).scalar_one(),sales)
        self.assertEqual((await self.db.execute(select(func.count(InventoryMovement.id)).where(InventoryMovement.company_id==self.company.id))).scalar_one(),moves)
        self.assertEqual(self.balance.quantity,100)
    async def test_expiration_grace_and_suspension_do_not_delete_or_extend_data(self):
        now=datetime.now(UTC);sub=self.subscription;sub.status='active';sub.current_period_ends_at=now-timedelta(hours=1);sub.grace_ends_at=now+timedelta(hours=1)
        self.assertEqual(effective_status(sub),'grace_period');self.assertEqual(effective_status(sub,now+timedelta(hours=2)),'expired')
        sub.status='suspended';self.assertEqual(effective_status(sub),'suspended')
        with self.assertRaises(HTTPException):await self.svc.license_action(self.company.id,LicenseInput(action='reactivate',reason='Expired cannot reactivate'))
        self.assertEqual(self.balance.quantity,100)
    async def test_paid_license_suspension_and_reactivation_preserve_expiry(self):
        invoice=await self.invoice();await self.svc.confirm(self.payment(invoice));end=self.subscription.current_period_ends_at
        await self.svc.license_action(self.company.id,LicenseInput(action='suspend',reason='Synthetic suspension'))
        self.assertEqual(self.subscription.status,'suspended')
        with self.assertRaises(HTTPException):await SubscriptionService(self.db).enforce_writes_allowed(self.company.id)
        await self.svc.license_action(self.company.id,LicenseInput(action='reactivate',reason='Synthetic resolution'))
        self.assertEqual(self.subscription.status,'active');self.assertEqual(self.subscription.current_period_ends_at,end)
    async def test_opt_in_feature_and_capacity_limits_preserve_legacy_businesses(self):
        await enforce_feature(self.db,self.company.id,'variants')
        invoice=await self.invoice();await self.svc.confirm(self.payment(invoice))
        await enforce_feature(self.db,self.company.id,'restaurant')
        with self.assertRaises(HTTPException):await enforce_feature(self.db,self.company.id,'variants')
        self.subscription.commercial_terms={**self.subscription.commercial_terms,'branch_limit':1,'employee_limit':1,'device_limit':1};await self.db.commit()
        for kind in ('branch','employee'):
            with self.subTest(kind=kind),self.assertRaises(HTTPException):await enforce_capacity(self.db,self.company.id,kind)
        self.device.claimed_at=datetime.now(UTC);self.device.status='active';await self.db.commit()
        with self.assertRaises(HTTPException):await enforce_capacity(self.db,self.company.id,'device')
        await enforce_capacity(self.db,self.company.id,'device',self.device.id)
    async def test_platform_role_restrictions_and_business_tokens_are_not_platform_sessions(self):
        for role in ('support','billing'):
            self.admin.role=role
            with self.assertRaises(HTTPException):permit(self.admin,'license')
        with self.assertRaises(HTTPException):await authenticate(self.db,create_access_token(str(self.user.id),self.user.email))
        self.admin.role='super_admin'
        result=await login(self.db,self.admin.email,'synthetic-platform-password')
        admin,session=await authenticate(self.db,result['access_token']);self.assertEqual(admin.id,self.admin.id)
        session.revoked_at=datetime.now(UTC);await self.db.commit()
        with self.assertRaises(HTTPException):await authenticate(self.db,result['access_token'])
    async def test_failed_platform_passwords_lock_and_disabled_accounts_reject(self):
        for _ in range(5):
            with self.assertRaises(HTTPException):await login(self.db,self.admin.email,'wrong-password')
        with self.assertRaises(HTTPException):await login(self.db,self.admin.email,'synthetic-platform-password')
        self.admin.locked_until=None;self.admin.active=False;await self.db.commit()
        with self.assertRaises(HTTPException):await login(self.db,self.admin.email,'synthetic-platform-password')
    async def test_notifications_are_deduplicated_and_billing_is_company_scoped(self):
        self.subscription.trial_ends_at=datetime.now(UTC)+timedelta(days=2);await self.db.commit()
        await self.svc.reminders();before=(await self.db.execute(select(func.count(BillingNotice.id)).where(BillingNotice.company_id==self.company.id))).scalar_one()
        await self.svc.reminders();after=(await self.db.execute(select(func.count(BillingNotice.id)).where(BillingNotice.company_id==self.company.id))).scalar_one()
        self.assertEqual(before,after)
        invoice=await self.invoice();await self.svc.confirm(self.payment(invoice))
        self.assertEqual((await self.svc.billing(uuid4()))['payments'],[])
        self.assertEqual((await self.svc.billing(self.company.id))['payments'][0]['currency'],'EUR')
    async def test_platform_http_auth_and_business_isolation(self):
        from app.main import app
        from app.db.session import get_db
        async def db_override():yield self.db
        app.dependency_overrides[get_db]=db_override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated.test') as client:
                owner=create_access_token(str(self.user.id),self.user.email)
                self.assertEqual((await client.get('/api/platform/dashboard',headers={'Authorization':'Bearer '+owner})).status_code,401)
                auth=await client.post('/api/platform/login',json={'email':self.admin.email,'password':'synthetic-platform-password'})
                self.assertEqual(auth.status_code,200);token=auth.json()['access_token']
                self.assertEqual((await client.get('/api/platform/dashboard',headers={'Authorization':'Bearer '+token})).status_code,200)
                self.assertEqual((await client.get('/api/subscriptions/billing/'+str(uuid4()),headers={'Authorization':'Bearer '+owner})).status_code,403)
                self.assertEqual((await client.get('/api/products/'+str(self.company.id),headers={'Authorization':'Bearer '+token})).status_code,401)
                self.assertEqual((await client.get('/api/subscriptions/billing/'+str(self.company.id),headers={'Authorization':'Bearer '+owner})).status_code,200)
        finally:app.dependency_overrides.clear()
    async def test_ledger_and_invoice_snapshots_are_database_protected(self):
        invoice=await self.invoice();await self.svc.confirm(self.payment(invoice))
        for table,column in (('billing_payments','amount'),('billing_invoices','amount')):
            with self.subTest(table=table),self.assertRaises(DBAPIError):
                async with self.db.begin_nested():await self.db.execute(text(f'UPDATE {table} SET {column}=0 WHERE company_id=:company'),{'company':self.company.id})
    async def test_failed_receipt_audit_rolls_back_payment_and_renewal(self):
        invoice=await self.invoice();request=self.payment(invoice)
        with patch.object(self.svc,'audit',side_effect=RuntimeError('synthetic audit failure')):
            with self.assertRaises(RuntimeError):await self.svc.confirm(request)
        await self.db.rollback()
        payments=(await self.db.execute(select(func.count(BillingPayment.id)).where(BillingPayment.request_id==request.request_id))).scalar_one()
        self.assertEqual(payments,0)
    async def test_commercial_subscription_page_and_bounded_signed_grace(self):
        invoice=await self.invoice();await self.svc.confirm(self.payment(invoice))
        self.subscription.grace_ends_at=datetime.now(UTC)+timedelta(hours=2);await self.db.commit()
        with patch('app.subscriptions.service.create_entitlement_snapshot_token',return_value='signed') as sign:
            page=await SubscriptionService(self.db).page(self.company.id)
        self.assertEqual(page['current']['plan_label'],'Synthetic quarterly')
        self.assertFalse(page['activation_available']);self.assertEqual(page['available_plans'],[])
        self.assertEqual(page['billing_preview']['currency'],'EUR')
        claims=sign.call_args.kwargs
        self.assertLessEqual(claims['offline_grace_expires_at'],self.subscription.grace_ends_at)
        self.assertFalse(claims['features']['variants']);self.assertEqual(claims['limits']['branch'],2)
    async def test_verified_late_legacy_payment_is_retained_without_replacing_commercial_terms(self):
        invoice=await self.invoice();await self.svc.confirm(self.payment(invoice));expiry=self.subscription.current_period_ends_at
        await SubscriptionService(self.db).apply_confirmed_payment(company_id=self.company.id,provider='fixture-provider',provider_reference='old-paid',
            plan='monthly',billing_snapshot={'currency':'USD','total_amount':Decimal('8'),'unit_price':Decimal('8'),'terminal_count':1},payload={'verified':True},status_reason='Verified callback')
        self.assertEqual(self.subscription.current_period_ends_at,expiry);self.assertEqual(self.subscription.plan,'commercial')
        receipt=(await self.db.execute(select(CompanySubscriptionHistory).where(CompanySubscriptionHistory.company_id==self.company.id,CompanySubscriptionHistory.action=='legacy_payment_needs_review'))).scalar_one()
        self.assertEqual(receipt.provider_reference,'old-paid')
    async def test_server_routes_enforce_features_and_branch_limit_for_business_owner(self):
        invoice=await self.invoice();await self.svc.confirm(self.payment(invoice))
        self.subscription.commercial_terms={**self.subscription.commercial_terms,'branch_limit':1};await self.db.commit()
        from app.main import app
        from app.db.session import get_db
        async def db_override():yield self.db
        app.dependency_overrides[get_db]=db_override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated.test',headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)}) as client:
                self.assertEqual((await client.post(f'/api/products/variants/{self.company.id}/{self.product.id}',json={'name':'Denied variant','selling_price':4})).status_code,403)
                self.assertEqual((await client.post('/api/inventory/branches',json={'company_id':str(self.company.id),'shop_id':str(self.shop.id),'name':'Over limit'})).status_code,402)
                self.assertEqual((await client.post('/api/subscriptions/activate',json={'company_id':str(self.company.id),'plan':'monthly'})).status_code,409)
                self.assertEqual((await client.get('/api/reports/financial-summary/'+str(self.company.id)+'?date_from=2026-01-01&date_to=2026-12-31')).status_code,403)
                access=await client.get('/api/subscriptions/access/'+str(self.company.id))
                self.assertEqual(access.status_code,200);self.assertFalse(access.json()['features']['variants'])
        finally:app.dependency_overrides.clear()
    async def test_currency_precision_and_overpayment_rejected_without_mutating_balances(self):
        invoice=await self.invoice()
        for amount in ('1.001','10.00'):
            with self.subTest(amount=amount),self.assertRaises(HTTPException):await self.svc.confirm(self.payment(invoice,amount=amount))
        self.assertEqual(await self.svc.paid(invoice),0)
    async def test_three_decimal_commercial_currency_does_not_round_into_legacy_summary(self):
        legacy=self.subscription.total_amount
        plan=await self.plan(currency='KWD',decimal_places=3,price='9.999')
        invoice=await self.invoice(plan);await self.svc.confirm(self.payment(invoice))
        self.assertEqual(self.subscription.total_amount,legacy)
        self.assertEqual(self.subscription.commercial_terms['price'],'9.999')
        self.assertEqual(await self.svc.paid(invoice),Decimal('9.999'))
        with patch('app.subscriptions.service.create_entitlement_snapshot_token',return_value='signed'):
            page=await SubscriptionService(self.db).page(self.company.id)
        self.assertEqual(page['billing_preview']['total_amount'],Decimal('9.999'))
    async def test_plan_below_existing_usage_cannot_be_invoiced_or_disable_existing_records(self):
        from app.models import Branch
        second=Branch(company_id=self.company.id,shop_id=self.shop.id,name='Existing second branch',active=True,deleted=False)
        self.db.add(second);await self.db.commit()
        plan=await self.plan(branch_limit=1)
        with self.assertRaises(HTTPException):await self.invoice(plan)
        self.assertTrue(second.active)
        self.assertEqual((await self.db.execute(select(func.count(BillingInvoice.id)).where(BillingInvoice.company_id==self.company.id))).scalar_one(),0)
    async def test_populated_commercial_migration_refuses_destructive_downgrade(self):
        import importlib.util
        from pathlib import Path
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        path=Path(__file__).resolve().parents[1]/'migrations/versions/p8a_commercial_billing.py'
        spec=importlib.util.spec_from_file_location('test_phase8_migration_guard',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        def check(sync_db):
            module.op=Operations(MigrationContext.configure(sync_db.connection()))
            with self.assertRaisesRegex(RuntimeError,'Commercial data exists'):module.downgrade()
        await self.db.run_sync(check)
        self.assertIsNotNone(await self.db.get(PlatformAdmin,self.admin.id))
    async def test_global_outstanding_report_and_history_pagination_use_server_totals(self):
        invoice=await self.invoice();await self.svc.confirm(self.payment(invoice,amount='4'))
        page=await self.svc.billing(self.company.id)
        self.assertEqual(page['outstanding_by_currency'],[{'currency':'EUR','amount':Decimal('5.99')}])
        old=await self.svc.billing(self.company.id,200)
        self.assertEqual(old['invoices'],[]);self.assertEqual(old['payments'],[])
        self.assertEqual(old['outstanding_by_currency'],page['outstanding_by_currency'])
    async def test_fractional_final_grace_second_signs_non_writable_not_extended_license(self):
        invoice=await self.invoice();await self.svc.confirm(self.payment(invoice))
        fixed=datetime(2026,10,20,12,0,0,100000,tzinfo=UTC)
        self.subscription.grace_ends_at=fixed+timedelta(microseconds=500000)
        with patch('app.subscriptions.service.datetime') as clock,patch('app.subscriptions.service.create_entitlement_snapshot_token',return_value='signed') as sign:
            clock.now.return_value=fixed
            snapshot=SubscriptionService(self.db).snapshot_for(self.subscription)
        self.assertFalse(snapshot['writes_allowed']);self.assertEqual(sign.call_args.kwargs['status'],'expired')
    async def test_wholesale_only_plan_can_create_and_edit_quotations_without_restaurant_license(self):
        plan=await self.plan(features={'wholesale':True});invoice=await self.invoice(plan);await self.svc.confirm(self.payment(invoice))
        from app.business_operations.service import BusinessService
        from app.business_operations.schema import ProfileInput
        await BusinessService(self.db,self.owner).save_profile(ProfileInput(profile='wholesale'))
        from app.main import app
        from app.db.session import get_db
        async def db_override():yield self.db
        app.dependency_overrides[get_db]=db_override
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://isolated.test',headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)}) as client:
                created=await client.post('/api/operations/orders',json={'branch_id':str(self.branch.id),'device_id':str(self.device.id),'request_id':str(uuid4()),'kind':'quotation'})
                self.assertEqual(created.status_code,200,created.text)
                order=created.json()
                added=await client.post(f'/api/operations/orders/{order["id"]}/items',json={'version':order['version'],'product_id':str(self.product.id),'quantity':'1'})
                self.assertEqual(added.status_code,200,added.text)
        finally:app.dependency_overrides.clear()
