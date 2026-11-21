"""Exact bounded allocations; plans are explicitly not posted tender acceptance."""
import unittest,random
from decimal import Decimal as D
from fastapi import HTTPException
from app.accounting.planning import amount,apportion,pricing,tenders,refunds
class AccountingPlanTests(unittest.TestCase):
    def test_integer_remainder_conservation_and_stable_order(self):
        rng=random.Random(110021)
        for _ in range(1000):
            weights=[(str(i),rng.randint(1,100000)) for i in range(rng.randint(1,20))];total=rng.randint(0,100000)
            result=apportion(total,weights);self.assertEqual(sum(result.values()),total);self.assertEqual(result,apportion(total,list(reversed(weights))))
            for key,w in weights:self.assertIn(result[key],{total*w//sum(v for _,v in weights),total*w//sum(v for _,v in weights)+1})
    def test_discount_tax_unit_and_minor_unit_invariants(self):
        lines=[{'id':'b','quantity':D('.5'),'factor':12,'price':2,'discount':D('.01'),'tax_rate':15},{'id':'a','quantity':1,'price':D('.05'),'tax_rate':0}]
        result=pricing(lines,2,False,D('.03'));self.assertEqual(result['items'][0]['base_quantity'],'6.0');self.assertEqual(D(result['subtotal'])+D(result['tax']),D(result['total']));self.assertEqual(D(result['discount']),D('.04'));self.assertFalse(result['posting_enabled'])
        again=pricing(list(reversed(lines)),2,False,D('.03'));self.assertEqual(result['tax'],again['tax']);self.assertEqual({r['id']:r for r in result['items']},{r['id']:r for r in again['items']})
        for places in range(5):
            value=pricing([{'id':'a','quantity':1,'price':13,'tax_rate':15}],places,True);self.assertEqual(D(value['subtotal'])+D(value['tax']),13)
        with self.assertRaises(HTTPException):pricing([{'id':'a','quantity':D('.001'),'factor':D('.1'),'price':100}],2,True)
        with self.assertRaises(HTTPException):pricing([{'id':'a','quantity':1,'price':1}],2,True,D('1'))
        with self.assertRaises(HTTPException):amount(0.1,2)
        with self.assertRaises(HTTPException):pricing([{'id':'a','quantity':1,'price':1,'tax_rate':D('1e-100000')}],2,True)
    def test_mixed_fx_tender_one_total_cash_change_and_no_provider_success(self):
        legs=[{'id':k,'method':m,'currency':'SYN','places':2,'applied':D('1'),'tendered':D('1.25') if m=='cash' else D('1'),'rate':D('3')} for k,m in [('a','cash'),('b','card'),('c','mobile')]]
        result=tenders(D('1'),2,legs);self.assertEqual([r['applied_base'] for r in result['legs']],['0.34','0.33','0.33']);self.assertEqual(result['legs'][0]['change_original'],'0.25');self.assertEqual(result,tenders(D('1'),2,list(reversed(legs))));self.assertFalse(result['posting_enabled']);self.assertTrue(all(not r['provider_confirmed'] for r in result['legs']))
        with self.assertRaises(HTTPException):tenders(D('1.01'),2,legs)
        with self.assertRaises(HTTPException):tenders(D('1'),2,[{**r,'quoted_base':D('.33')} for r in legs])
        with self.assertRaises(HTTPException):tenders(D('1'),2,[{**legs[0],'rate':D('1e-100000')}])
    def test_cumulative_refund_debt_first_caps_and_original_currency_residual(self):
        legs=[{'id':'credit','method':'credit','places':2,'original':D('.40'),'applied_base':D('.40')},{'id':'cash','method':'cash','places':2,'original':D('.60'),'applied_base':D('.60')}]
        result=refunds(D('.50'),2,legs,D('.40'));self.assertEqual(result['allocations'],[{'id':'credit','kind':'debt_reduction','base':'0.40','original':'0.40'},{'id':'cash','kind':'paid_refund','base':'0.10','original':'0.10'}])
        with self.assertRaises(HTTPException):refunds(D('1'),2,legs,0)
        with self.assertRaises(HTTPException):refunds(D('1.01'),2,legs,D('.40'))
        leg={'id':'fx','method':'cash','places':2,'original':D('1'),'applied_base':D('.33'),'refunded_base':D('.22'),'refunded_original':D('.67')}
        final=refunds(D('.11'),2,[leg],0);self.assertEqual(final['allocations'][0]['original'],'0.33');self.assertFalse(final['posting_enabled'])
        with self.assertRaises(HTTPException):refunds(D('.11'),2,[{**leg,'refunded_original':D('.66')}],0)
        with self.assertRaises(HTTPException):refunds(D('.01'),2,[{'id':'tiny','method':'cash','places':0,'original':D('1'),'applied_base':D('100')}],0)
