"""Read-only discount/custom-unit/currency proposals preserve accepted v1 guards."""
import unittest
from decimal import Decimal
from datetime import datetime,timedelta,timezone
from sqlalchemy import select,func
from app.models import CompanySetting,CompanyCurrency,CurrencyExchangeRate,Sale,InventoryMovement
import test_phase11_quotations as fixtures
class PricingReviewTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.QuotationTests.asyncSetUp
    cleanup=fixtures.QuotationTests.cleanup
    async def test_configured_unit_discount_and_fx_review_do_not_change_quote_or_stock(self):
        self.product.purchase_unit='box';self.product.units_per_purchase=12
        settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.company.id))).scalar_one();settings.tax_rate=15;settings.tax_inclusive=False;settings.multi_currency_enabled=True
        currency=CompanyCurrency(company_id=self.company.id,code='JPY',display_name='Synthetic yen',symbol='JPY',decimal_places=0,active=True,is_base=False);self.db.add(currency);await self.db.flush()
        self.db.add(CurrencyExchangeRate(company_id=self.company.id,currency_id=currency.id,currency_code="JPY",foreign_units_per_base=150,effective_at=datetime.now(timezone.utc)-timedelta(days=1),created_by_user_id=self.user.id));await self.db.commit()
        before=(await self.svc.order_out(await self.svc.order(self.order['id'])))
        body={'version':self.order['version'],'lines':[{'item_id':str(self.order['items'][0]['id']),'quantity':'.5','unit':'box','discount':'1.00'}],'sale_discount':'2.00','currency_code':'JPY'}
        response=await self.client.post(f"/api/operations/orders/{self.order['id']}/pricing/review",json=body);self.assertEqual(response.status_code,200,response.text);data=response.json();self.assertEqual(data['total'],'79.35');self.assertEqual(data['display_total'],'11903');self.assertFalse(data['conversion_enabled']);self.assertFalse(data['posting_enabled']);self.assertTrue(data['review_only'])
        after=await self.svc.order_out(await self.svc.order(self.order['id']));self.assertEqual(before,after);self.assertEqual(self.balance.quantity,100)
        body['lines'][0]['unit']='invented';denied=await self.client.post(f"/api/operations/orders/{self.order['id']}/pricing/review",json=body);self.assertEqual(denied.status_code,422)
    async def test_zero_decimal_review_remains_outside_accepted_conversion(self):
        base=(await self.db.execute(select(CompanyCurrency).where(CompanyCurrency.company_id==self.company.id,CompanyCurrency.is_base.is_(True)))).scalar_one();base.decimal_places=0;await self.db.commit()
        body={'version':self.order['version'],'lines':[{'item_id':str(self.order['items'][0]['id']),'quantity':'1','unit':'each','discount':'1'}]}
        r=await self.client.post(f"/api/operations/orders/{self.order['id']}/pricing/review",json=body);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['minor_unit_places'],0);self.assertFalse(r.json()['conversion_enabled'])
