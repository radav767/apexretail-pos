"""First close/recovery precision disclosure never rewrites stored evidence."""
import unittest
from uuid import uuid4,UUID
from sqlalchemy import select
from decimal import Decimal
from app.models import CompanyCurrency,CashierShiftCurrencySnapshot
import test_phase11_split_shifts as fixtures
class ShiftDisclosureTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=fixtures.SplitShiftTests.asyncSetUp
    cleanup=fixtures.SplitShiftTests.cleanup
    open_shift=fixtures.SplitShiftTests.open_shift
    async def currencies(self):
        for places in range(5):self.db.add(CompanyCurrency(company_id=self.c,code='SC'+str(places),display_name='Synthetic precision',symbol='S',decimal_places=places,cash_accepted=True,active=True))
        await self.db.commit()
    async def test_first_close_and_fresh_replay_have_identical_original_unit_fields(self):
        await self.currencies();opening=[{'currency_code':'USD','amount':'20'}]+[{'currency_code':'SC'+str(p),'amount':'1'+('.'+'1'*p if p else '')} for p in range(5)]
        response=await self.client.post('/api/shifts/open',headers=self.cashier_headers,json={'opening_balances':opening,'idempotency_key':str(uuid4())});self.assertEqual(response.status_code,200,response.text);sid=response.json()['id']
        command={'counted_balances':opening,'confirmed':True,'idempotency_key':str(uuid4())};first=await self.client.post('/api/shifts/'+sid+'/close',headers=self.cashier_headers,json=command);self.assertEqual(first.status_code,200,first.text)
        self.db.expunge_all()
        replay=await self.client.post('/api/shifts/'+sid+'/close',headers=self.cashier_headers,json=command);self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(first.json()['currencies'],replay.json()['currencies'])
        for p in range(5):
            row=next(r for r in replay.json()['currencies'] if r['currency_code']=='SC'+str(p));self.assertEqual(row['opening_float'],opening[p+1]['amount']);self.assertEqual(Decimal(row['variance']),0)
    async def test_unrepresentable_historical_fraction_remains_visible(self):
        from app.shifts.service import disclosed_original_units
        for places in range(4):
            result=disclosed_original_units(Decimal('1.0001'),places)
            self.assertEqual(result,Decimal('1.0001'));self.assertEqual(result.as_tuple().exponent,-4)
        self.assertIsNone(disclosed_original_units(None,2))
