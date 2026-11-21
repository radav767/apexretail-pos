"""Historical split ledger reads must never rewrite receipts or mutate transactions."""
import unittest
from uuid import UUID,uuid4
from decimal import Decimal
from sqlalchemy import select
from app.models import Sale,CompanySubscription,User,Branch,Employee
import test_phase11_split_refunds as fixtures

class SplitHistoryTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.SplitRefundTests.cleanup
    asyncSetUp=fixtures.SplitRefundTests.asyncSetUp
    checkout=fixtures.SplitRefundTests.checkout
    original=fixtures.SplitRefundTests.original
    command=fixtures.SplitRefundTests.command
    post=fixtures.SplitRefundTests.post
    stock=fixtures.SplitRefundTests.stock
    async def read(self,sale=None,query='',status=200,headers=None,company=None):
        response=await self.client.get(f'/api/sales/v2/split/history/{company or self.c}/{sale or self.sid}'+query,headers=headers)
        self.assertEqual(response.status_code,status,response.text);return response.json()
    async def test_paginated_original_and_refund_read_conserve_ledgers_without_reprint(self):
        await self.original()
        a=await self.post(self.command('.25','3',[(self.credit,'debt_reduction','3','3')]))
        b=await self.post(self.command('.25','3',[(self.credit,'debt_reduction','1','1'),(self.cash,'paid_refund','2','2')]))
        result=await self.read(query='?limit=1');self.assertTrue(result['ledger_matches']);self.assertEqual(result['refund_count'],2);self.assertEqual(len(result['refunds']),1);self.assertFalse(result['reprint_recorded']);self.assertFalse(result['posting_enabled'])
        self.assertEqual({key:Decimal(result['totals'][key]) for key in ('initial_cash','original_credit','credited','outstanding','refund_total','cash_refunded')},{'initial_cash':8,'original_credit':4,'credited':4,'outstanding':0,'refund_total':6,'cash_refunded':2})
        self.assertEqual(Decimal(result['net_billed']),6);self.assertEqual(Decimal(result['net_applied_cash_base']),6)
        page=await self.read(query='?limit=1&offset=1');self.assertEqual({page['refunds'][0]['id'],result['refunds'][0]['id']},{a['sale']['id'],b['sale']['id']})
        child=await self.read(sale=a['sale']['id']);self.assertEqual(child['original_sale_id'],str(self.sid));self.assertTrue(child['ledger_matches']);self.assertEqual(len(child['legs']),2)
        self.assertEqual(await self.stock(),Decimal('99.5'))
        for sid in [self.sid,UUID(a['sale']['id']),UUID(b['sale']['id'])]:
            sale=await self.db.get(Sale,sid,populate_existing=True);self.assertEqual(sale.reprint_count,0)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit();self.settings.split_checkout_mode='disabled'
        self.assertEqual((await self.read())['totals'],result['totals'])
    async def test_tenant_branch_permission_revocation_and_bounds(self):
        await self.original();await self.read(company=uuid4(),status=403);await self.read(query='?limit=101',status=422)
        from app.auth.security import create_employee_access_token
        employee=await self.db.get(Employee,self.e);employee.role='inventory_clerk';employee.permissions={'sales_history_view':False,'sales_refund':False}
        await self.db.commit();bearer=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='inventory_clerk')
        await self.read(status=403,headers={'Authorization':'Bearer '+bearer})
        employee=await self.db.get(Employee,self.e);employee.role='cashier';employee.permissions={'sales_history_view':True,'sales_refund':False}
        branch=await self.db.get(Branch,self.b);other=Branch(company_id=self.c,shop_id=branch.shop_id,name='Synthetic historical scope');self.db.add(other);await self.db.flush();employee.branch_id=other.id;await self.db.commit()
        bearer=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='cashier');await self.read(status=403,headers={'Authorization':'Bearer '+bearer})
        user=await self.db.get(User,self.u);user.session_version+=1;await self.db.commit();await self.read(status=401)
    async def test_original_branch_reader_sees_ledger_totals_without_foreign_refund_identifiers(self):
        await self.original()
        from app.models import Device
        branch=await self.db.get(Branch,self.b);other=Branch(company_id=self.c,shop_id=branch.shop_id,name='Synthetic return branch');self.db.add(other);await self.db.flush()
        device=Device(company_id=self.c,shop_id=branch.shop_id,branch_id=other.id,name='Synthetic cross-branch return register',device_key=str(uuid4()));self.db.add(device);await self.db.commit()
        command=self.command('.25','3',[(self.credit,'debt_reduction','3','3')]);command.update(branch_id=str(other.id),device_id=str(device.id),device_key=device.device_key,assignment_revision=device.assignment_revision)
        returned=await self.post(command)
        self.assertEqual((await self.read())['refund_count'],1)
        employee=await self.db.get(Employee,self.e);employee.permissions={'sales_history_view':True,'sales_refund':False};await self.db.commit()
        from app.auth.security import create_employee_access_token
        bearer=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role=employee.role);headers={'Authorization':'Bearer '+bearer}
        result=await self.read(headers=headers);self.assertTrue(result['ledger_matches']);self.assertEqual(result['refunds'],[]);self.assertEqual(result['refund_count'],0);self.assertEqual(Decimal(result['totals']['refund_total']),3)
        await self.read(sale=returned['sale']['id'],status=403,headers=headers)
