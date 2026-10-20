"""Mandatory-shift scenarios through real HTTPS, on new synthetic tenants only."""
import json
from pathlib import Path
import secrets
import re
from uuid import uuid4
from decimal import Decimal
import httpx

ROOT=Path('/tmp/apexretail-phase7f-runtime')
BASE='https://localhost:18770/api'

def main():
    run=str(uuid4());private=ROOT/f'phase7g-{run}.json';state={'run':run};results=[]
    def save():private.write_text(json.dumps(state,indent=2));private.chmod(0o600)
    def check(name,condition=True):
        results.append({'check':name,'result':'PASS' if condition else 'FAIL'})
        (ROOT/'phase7g-results.json').write_text(json.dumps(results,indent=2))
        if not condition:raise RuntimeError(name)
    with httpx.Client(verify=str(ROOT/'keys/local-ca.pem'),trust_env=False,timeout=45) as client:
        identity=client.get(BASE+'/staging-identity');identity.raise_for_status()
        if identity.json()['database']!='apexretail_phase7f_acceptance':raise RuntimeError('Refusing unexpected database')
        def call(method,path,token=None,data=None,status=200):
            response=client.request(method,BASE+path,json=data,headers={'Authorization':'Bearer '+token} if token else {})
            if response.status_code!=status:raise RuntimeError(f'{method} {path}: expected {status}, got {response.status_code}: {response.text[:200]}')
            return response.json() if 'json' in response.headers.get('content-type','') else response.content
        password=secrets.token_urlsafe(24);email=f'owner-{run}@phase7g.example.com'
        reg=call('POST','/auth/register',data={'owner_name':'Synthetic 7G Owner','owner_pin':'4321','business_name':'PHASE 7G SYNTHETIC ACCEPTANCE',
            'business_type':'Retail','country':'Zimbabwe','phone':'+000000000','email':email,'password':password,'confirm_password':password,
            'base_currency_code':'USD','base_currency_symbol':'$','base_currency_decimal_places':2,'device_key':str(uuid4())})
        state.update(email=email,password=password,registration=reg);save()
        owner=reg['token'];company=reg['company']['id'];branch=reg['branch']['id'];device=reg['device']
        updated=call('PATCH',f'/settings/{company}',owner,{'shift_enforcement_enabled':True,'shift_required_from':None})
        check('Mandatory enforcement ON only for new synthetic staging tenant',updated['shift_enforcement_enabled'] is True)
        state['cashiers']={}
        for name,pin,denied in [('A','1357',False),('B','2468',False),('Restricted','9753',True)]:
            state['cashiers'][name]=call('POST','/employees',owner,{'company_id':company,'branch_id':branch,'shop_id':reg['shop']['id'],
                'name':'Synthetic Cashier '+name,'pin':pin,'role':'cashier','permissions':{'shifts_open':not denied,'shifts_close':not denied,'z_reports_view':not denied}})
        save()
        product=call('POST','/products',owner,{'company_id':company,'branch_id':branch,'create_request_key':run,'name':'Shift acceptance stock','cost_price':'4','selling_price':'10','stock_qty':'20'})
        state['product']=product;save()
        def login(name,pin):
            session=call('POST','/employees/pin-login',data={'company_id':company,'branch_id':branch,'shop_id':reg['shop']['id'],
                'device_id':device['id'],'device_key':device['device_key'],'pin':pin})
            check('PIN authentication '+name,session['id']==state['cashiers'][name]['id'])
            return session['access_token']
        def sale(name,shift=None):
            return {'company_id':company,'branch_id':branch,'employee_id':state['cashiers'][name]['id'],'device_id':device['id'],
                'device_key':device['device_key'],'shift_id':shift,'payment_method':'cash','amount_received':'10','client_sale_id':str(uuid4()),
                'items':[{'product_id':product['id'],'quantity':'1','unit_price':'10'}]}
        def close(shift,count,key):return {'confirmed':True,'idempotency_key':run+key,'counted_balances':[{'currency_code':'USD','amount':count}]}
        a=login('A','1357')
        check('A initially has no inherited shift',call('GET','/shifts/current',a) is None)
        call('POST','/sales',a,sale('A'),status=409);check('Server rejects sale without active shift')
        sa=call('POST','/shifts/open',a,{'idempotency_key':run+'open-A'})
        check('Omitted opening amount defaults to zero',Decimal(sa['currencies'][0]['opening_float'])==0)
        again=call('POST','/shifts/open',a,{'idempotency_key':run+'open-A'})
        check('Repeated shift open is idempotent',again['id']==sa['id'])
        payload=sale('A',sa['id']);state['sale_payload']=payload;state['shift_a']=sa;save()
        completed=call('POST','/sales',a,payload);retry=call('POST','/sales',a,payload)
        check('Cash sale belongs to A original shift',completed['shift_id']==sa['id'] and completed['employee_id']==state['cashiers']['A']['id'])
        check('Sale retry returns original sale',completed['id']==retry['id'])
        call('POST','/employees/session/logout',a)
        b=login('B','2468')
        check('B never inherits A shift',call('GET','/shifts/current',b) is None)
        call('POST','/shifts/open',b,{'idempotency_key':run+'blocked-B'},status=409);check('Shared register cannot have overlapping ownership')
        call('POST','/sales',b,sale('B',sa['id']),status=409);check('B cannot sell against A shift')
        call('POST',f'/shifts/{sa["id"]}/close',b,close(sa,'10','unauthorized'),status=403);check('B cannot close A shift')
        call('POST','/employees/session/logout',b)
        a=login('A','1357')
        closed_a=call('POST',f'/shifts/{sa["id"]}/close',a,close(sa,'9','close-A'))
        check('Own shift closes with shortage recorded',closed_a['status']=='closed' and Decimal(closed_a['currencies'][0]['expected_cash'])==10 and Decimal(closed_a['currencies'][0]['variance'])==-1)
        repeat_close=call('POST',f'/shifts/{sa["id"]}/close',a,close(sa,'9','close-A'))
        state['closed_a']=closed_a;state['repeated_close_a']=repeat_close;save()
        def canonical(value):
            if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
            if isinstance(value,list):return [canonical(v) for v in value]
            if isinstance(value,str) and re.fullmatch(r'-?\d+(\.\d+)?',value):return Decimal(value)
            return value
        check('Closing is idempotent (normalized decimal representations)',canonical(repeat_close)==canonical(closed_a))
        check('Closed shift returns to no-active-shift state',call('GET','/shifts/current',a) is None)
        call('POST','/sales',a,sale('A',sa['id']),status=409);check('Closed shift rejects new sales')
        report=call('GET',f'/shifts/{sa["id"]}/z-report',a);pdf=call('GET',f'/shifts/{sa["id"]}/z-report.pdf',a)
        check('Immutable report preserves shortage',Decimal(report['currencies'][0]['variance'])==-1 and pdf.startswith(b'%PDF'))
        for width in ['58mm','80mm']:
            thermal=call('GET',f'/shifts/{sa["id"]}/z-report/thermal?paper_width={width}',a)
            check(width+' report output generation',b'<html' in thermal.lower())
        call('POST','/employees/session/logout',a)
        b=login('B','2468')
        sb=call('POST','/shifts/open',b,{'idempotency_key':run+'open-B','opening_balances':[{'currency_code':'USD','amount':'25'}]})
        check('B opens independent nonzero shift after handover',sb['id']!=sa['id'] and sb['employee_id']!=sa['employee_id'] and Decimal(sb['currencies'][0]['opening_float'])==25)
        closed_b=call('POST',f'/shifts/{sb["id"]}/close',b,close(sb,'27','close-B'))
        check('Overage recorded without changing sales',Decimal(closed_b['currencies'][0]['variance'])==2)
        call('POST','/employees/session/logout',b)
        restricted=login('Restricted','9753')
        call('POST','/shifts/open',restricted,{'idempotency_key':run+'restricted'},status=403);check('Opening permission enforced by backend')
        call('POST',f'/shifts/{sb["id"]}/close',restricted,close(sb,'27','restricted-close'),status=403);check('Closing permission enforced by backend')
        call('GET',f'/shifts/{sa["id"]}/z-report',restricted,status=403);check('Z Report access restricted')
        call('POST','/employees/session/logout',restricted)
        stock=call('GET',f'/inventory/branch-overview/{company}?branch_id={branch}',owner)
        check('Rejected/retried sales do not duplicate stock deduction',Decimal(next(r['quantity'] for r in stock if r['product_id']==product['id']))==19)
        state['completed']=True;state['results']=results;save()
        (ROOT/'phase7g-current.json').write_text(json.dumps({'private_fixture':str(private)}));(ROOT/'phase7g-current.json').chmod(0o600)
    print(json.dumps({'checks_passed':len(results),'database':'apexretail_phase7f_acceptance','production_modified':False}))

if __name__=='__main__':main()
