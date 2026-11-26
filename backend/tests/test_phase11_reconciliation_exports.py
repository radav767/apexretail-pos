"""Real API and persisted synthetic ledger export acceptance; outer rollback."""
import csv
import hashlib
import io
import json
import unittest
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
from zipfile import ZipFile
from sqlalchemy import select
from app.models import Branch,Product,Sale,User
from app.accounting.exports import package,csv_bytes
from app.reports.service import csv_cell
import test_phase11_tender_flows as fixtures


class ExportEncodingTests(unittest.TestCase):
    def test_untrusted_text_and_typed_negative_money(self):
        for value in ['=1+1','+cmd','-cmd','@SUM(A1)',' =1','\t harmless','\r=1','\n=1','\ufeff=1',' \t@cmd','\u2003=1',' \ufeff =1','\x00=1',' \x00@cmd','\x7f=1']:
            self.assertTrue(csv_cell(value).startswith("'"),repr(value))
        rows=list(csv.reader(io.StringIO(csv_bytes([{'label':' \t=1','money':'-1.25'}],('label','money'),{'money'}).decode())))
        self.assertEqual(rows[1],["' \t=1",'-1.25'])
        with self.assertRaises(Exception):csv_bytes([{'money':'NaN'}],('money',),{'money'})


class ReconciliationExportTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.TenderFlowTests.cleanup
    asyncSetUp=fixtures.TenderFlowTests.asyncSetUp
    checkout=fixtures.TenderFlowTests.checkout
    original=fixtures.TenderFlowTests.original
    command=fixtures.TenderFlowTests.command
    post=fixtures.TenderFlowTests.post
    stock=fixtures.TenderFlowTests.stock
    debt=fixtures.TenderFlowTests.debt
    flow=fixtures.TenderFlowTests.flow

    async def download(self,**params):
        t=datetime.now(timezone.utc)
        return await self.client.get(f'/api/reports/reconciliation/{self.c}/export.zip',params={'start':(t-timedelta(days=1)).isoformat(),'end':(t+timedelta(seconds=1)).isoformat(),**params})

    def unpack(self,response):
        self.assertEqual(response.status_code,200,response.text if response.status_code!=200 else '')
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(response.headers['x-content-sha256'],hashlib.sha256(response.content).hexdigest())
        archive=ZipFile(io.BytesIO(response.content));manifest=json.loads(archive.read('manifest.json'))
        for name,meta in manifest['files'].items():
            self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),meta['sha256'])
        return json.loads(archive.read('snapshot.json')),manifest,archive

    async def test_export_agrees_with_dated_payment_collection_refund_ledger_and_never_mutates(self):
        await fixtures.TenderFlowTests.test_dated_payment_collection_refund_boundaries_and_replay_never_multiply_revenue(self)
        t=datetime(2004,3,1,tzinfo=timezone.utc)
        before=await self.stock()
        response=await self.download(start=t.isoformat(),end=(t+timedelta(days=3)).isoformat())
        snapshot,manifest,archive=self.unpack(response)
        report=await self.flow(t,t+timedelta(days=3),limit=200)
        for key in ('events','totals','cash_original_units','event_count'):self.assertEqual(snapshot[key],report[key])
        self.assertNotIn('revenue',snapshot) # no cost/profit disclosure under revenue authority
        self.assertEqual(snapshot['receipt_count'],2)
        self.assertEqual(sum(Decimal(r['billed']) for r in snapshot['receipts']),6)
        self.assertEqual({r['kind'] for r in snapshot['events']},{'original_payment','credit_origination','credit_collection','paid_refund','debt_reduction'})
        self.assertEqual(await self.stock(),before)
        self.assertEqual(package(snapshot),response.content)
        product=await self.db.get(Product,self.p);product.name='Changed current catalog';product.selling_price=999;await self.db.commit()
        again,_,_=self.unpack(await self.download(start=t.isoformat(),end=(t+timedelta(days=3)).isoformat()))
        for key in ('events','receipts','totals'):self.assertEqual(again[key],snapshot[key])
        self.assertEqual(archive.read('snapshot.json'),json.dumps(snapshot,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode())

    async def test_cash_change_and_two_fx_residuals_exact_refund_agree(self):
        await fixtures.TenderFlowTests.test_two_fx_residuals_and_final_refund_do_not_become_debt_or_hidden_cash(self)
        snapshot,_,_=self.unpack(await self.download())
        cash=next(r for r in snapshot['totals'] if r['method']=='cash' and r['base_code']=='USD')
        self.assertEqual(Decimal(cash['applied_base']),0)
        self.assertEqual(Decimal(cash['known_allocation_variance']),Decimal('0'))
        for row in snapshot['events']:
            if row['drawer_valuation'] is not None:
                self.assertEqual(Decimal(row['drawer_valuation']),Decimal(row['applied_base'])-Decimal(row['allocation_variance'])+Decimal(row['tender_change_variance']))

    async def test_tax_partial_final_refund_pennies_remain_separate_from_cash_and_debt(self):
        await fixtures.fixtures.SplitRefundTests.test_original_fx_and_tax_penny_residuals_survive_configuration_change(self)
        snapshot,_,archive=self.unpack(await self.download())
        rows=[row for row in snapshot['receipts'] if row['base_code']=='USD']
        self.assertEqual(len(rows),4)
        self.assertEqual(sum(Decimal(row['tax']) for row in rows if row['kind']=='sale'),Decimal('.02'))
        self.assertEqual(sum(Decimal(row['tax']) for row in rows if row['kind']=='refund'),Decimal('-.02'))
        self.assertEqual(sum(Decimal(row['billed']) for row in rows),0)
        totals=list(csv.DictReader(io.StringIO(archive.read('receipt-totals.csv').decode())))
        self.assertEqual(sum(Decimal(row['billed']) for row in totals if row['base_code']=='USD'),0)
        self.assertEqual(sum(Decimal(row['tax']) for row in totals if row['base_code']=='USD'),0)
        self.assertEqual(await self.stock(),100)

    async def test_scope_permission_unknown_history_and_revocation(self):
        snapshot,_,_=self.unpack(await self.download())
        legacy=next(r for r in snapshot['events'] if r['source_id']==str(self.sale.id))
        self.assertTrue(legacy['unknown_provenance']);self.assertIsNone(legacy['rate'])
        self.assertEqual((await self.client.get(f'/api/reports/reconciliation/{uuid4()}/export.zip',params={'start':snapshot['scope']['start'],'end':snapshot['scope']['end']})).status_code,403)
        self.assertEqual((await self.download(branch_id=str(uuid4()))).status_code,404)
        from app.auth.security import create_employee_access_token
        token=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='cashier')
        path=f'/api/reports/reconciliation/{self.c}/export.zip'
        bounds={'start':snapshot['scope']['start'],'end':snapshot['scope']['end']}
        self.assertEqual((await self.client.get(path,params=bounds,headers={'Authorization':'Bearer '+token})).status_code,403)
        # Authorized employee is forcibly scoped to their own branch.
        employee=self.employee;employee.permissions={**employee.permissions,'revenue_view':True,'credit_settlements':True};await self.db.commit()
        own=await self.client.get(path,params=bounds,headers={'Authorization':'Bearer '+token})
        own_snapshot,_,_=self.unpack(own);self.assertEqual(own_snapshot['scope']['branch'],str(self.b))
        other=Branch(company_id=self.c,shop_id=self.shop.id,name='Other synthetic branch');self.db.add(other);await self.db.flush()
        self.db.add(Sale(company_id=self.c,branch_id=other.id,receipt_number='SCOPE-'+uuid4().hex,total_amount=999,subtotal_amount=999,tax_amount=0,payment_method='cash',created_at=datetime.now(timezone.utc)))
        await self.db.commit()
        all_branches,_,_=self.unpack(await self.download());self.assertEqual(all_branches['event_count'],2)
        scoped,_,_=self.unpack(await self.client.get(path,params=bounds,headers={'Authorization':'Bearer '+token}));self.assertEqual(scoped['event_count'],1)
        self.assertTrue(all(row['branch_id']==str(self.b) for row in scoped['receipts']))
        self.assertEqual((await self.client.get(path,params={**bounds,'branch_id':str(other.id)},headers={'Authorization':'Bearer '+token})).status_code,403)
        user=await self.db.get(User,self.u);user.session_version+=1;await self.db.commit()
        self.assertEqual((await self.download()).status_code,401)

    async def test_single_snapshot_pages_formula_text_limits_and_inflight_revocation(self):
        # Historical fixture rows are deliberately synthetic, no transaction guard bypass.
        for index in range(205):
            self.db.add(Sale(company_id=self.c,branch_id=self.b,receipt_number=f' =SYN-{uuid4().hex}',total_amount=1,subtotal_amount=1,tax_amount=0,payment_method='cash',created_at=datetime.now(timezone.utc)))
        await self.db.commit()
        snapshot,manifest,archive=self.unpack(await self.download())
        pages=[name for name in manifest['files'] if name.startswith('events-')]
        self.assertEqual(len(pages),2)
        rows=[r for name in sorted(pages) for r in csv.DictReader(io.StringIO(archive.read(name).decode()))]
        self.assertEqual(len(rows),snapshot['event_count']);self.assertEqual(len({r['event_id'] for r in rows}),len(rows))
        self.assertTrue(all(r['receipt_number'].startswith("'") for r in rows if 'SYN-' in r['receipt_number']))
        self.assertEqual(len(snapshot['receipts']),snapshot['receipt_count'])
        with patch('app.accounting.exports.MAX_ROWS',1):self.assertEqual((await self.download()).status_code,422)
        with patch('app.accounting.exports.MAX_BYTES',1):self.assertEqual((await self.download()).status_code,422)
        from app.accounting import exports
        real_execute=self.db.execute
        async def execute(statement,*args,**kwargs):
            result=await real_execute(statement,*args,**kwargs)
            if statement is exports.EXPORT_SQL:
                from sqlalchemy import text
                await real_execute(text('UPDATE users SET session_version=session_version+1 WHERE id=:id'),{'id':self.u})
            return result
        with patch.object(self.db,'execute',execute):self.assertEqual((await self.download()).status_code,401)
