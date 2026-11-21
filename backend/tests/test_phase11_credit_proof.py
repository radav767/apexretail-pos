"""Single-statement reconciliation reads real collection/refund evidence once."""
import unittest
from decimal import Decimal
from sqlalchemy import select
from app.models import CompanySubscription
import test_phase11_tax_credit_refunds as fixtures
class CreditProofTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.TaxCreditRefundTests.asyncSetUp
    cleanup=fixtures.TaxCreditRefundTests.cleanup
    sell=fixtures.TaxCreditRefundTests.sell
    debt=fixtures.TaxCreditRefundTests.debt
    collect=fixtures.TaxCreditRefundTests.collect
    refund=fixtures.TaxCreditRefundTests.refund
    async def test_collection_credit_note_projection_and_expired_read_are_conserved(self):
        sale,items=await self.sell('credit');debt=await self.debt(sale);await self.collect(debt,Decimal('.05'));await self.sales.create_refund(self.refund(sale,items[0]),actor=self.owner)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one();sub.status='expired';await self.db.commit()
        response=await self.client.get(f'/api/reports/credit-reconciliation/{self.company.id}');self.assertEqual(response.status_code,200,response.text);data=response.json();self.assertFalse(data['repair_performed']);self.assertEqual(data['read_consistency'],'single_statement');row=data['items'][0];self.assertTrue(row['ledger_matches']);self.assertTrue(row['projection_valid']);self.assertEqual(Decimal(row['original'])-Decimal(row['collected'])-Decimal(row['credited']),Decimal(row['outstanding']))
        denied=await self.client.get('/api/reports/credit-reconciliation/11111111-1111-4111-8111-111111111111');self.assertEqual(denied.status_code,403)
    async def test_unproved_legacy_projection_requires_review_without_repair(self):
        sale,_=await self.sell('credit');debt=await self.debt(sale)
        debt.amount_settled=Decimal('.01');debt.outstanding_balance=debt.original_amount-Decimal('.01');debt.status='partially_paid';await self.db.commit()
        response=await self.client.get(f'/api/reports/credit-reconciliation/{self.company.id}');self.assertEqual(response.status_code,200,response.text)
        row=response.json()['items'][0];self.assertTrue(row['projection_valid']);self.assertFalse(row['ledger_matches']);self.assertEqual(row['status'],'provenance_review_required')
        await self.db.refresh(debt);self.assertEqual(debt.amount_settled,Decimal('.01'))
