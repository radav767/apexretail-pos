"""Real HTTPS acceptance checks with synthetic accounts; fixed staging target only."""
import json
from pathlib import Path
import secrets
import uuid
from datetime import datetime, timezone
from decimal import Decimal
import httpx

ROOT=Path('/tmp/apexretail-phase7f-runtime')
BASE='https://localhost:18770/api'
PRIVATE=ROOT/'acceptance-accounts.json'

def main():
    state=json.loads(PRIVATE.read_text()) if PRIVATE.exists() else {'accounts':[]}
    checks=[]
    def save():
        PRIVATE.write_text(json.dumps(state,indent=2));PRIVATE.chmod(0o600)
    def check(name, condition):
        checks.append({'check':name,'result':'PASS' if condition else 'FAIL'})
        (ROOT/'acceptance-api-results.json').write_text(json.dumps(checks,indent=2))
        if not condition: raise RuntimeError('Acceptance failure: '+name)
    with httpx.Client(verify=str(ROOT/'keys/local-ca.pem'),trust_env=False,timeout=60) as client:
        identity=client.get(BASE+'/staging-identity');identity.raise_for_status()
        check('Separate staging database and runtime role',identity.json()['database']=='apexretail_phase7f_acceptance' and identity.json()['role']=='apex_user')
        def call(method,path,token=None,data=None,expected=200):
            response=client.request(method,BASE+path,headers={'Authorization':'Bearer '+token} if token else {},json=data)
            if response.status_code!=expected:
                raise RuntimeError(f'{method} {path}: expected {expected}, got {response.status_code}: {response.text[:300]}')
            return response
        for index in range(len(state['accounts']),2):
            password=secrets.token_urlsafe(24); email=f'owner{index+1}@phase7f.example.com'
            registration={'owner_name':f'Synthetic Owner {index+1}','owner_pin':'4321','business_name':f'PHASE 7F SYNTHETIC {index+1}',
                'business_type':'Retail','country':'Zimbabwe','phone':'+000000000','email':email,'password':password,'confirm_password':password,
                'base_currency_code':'USD','base_currency_symbol':'$','base_currency_decimal_places':2,'device_key':str(uuid.uuid4())}
            response=call('POST','/auth/register',data=registration).json()
            state['accounts'].append({'email':email,'password':password,'pin':'4321','registration':response});save()
        first,other=state['accounts'];reg=first['registration']; company=reg['company']['id'];branch=reg['branch']['id'];owner=reg['token']
        check('Two synthetic tenants registered through real API',company!=other['registration']['company']['id'])
        login=call('POST','/auth/login',data={'email':first['email'],'password':first['password']}).json()
        owner=login['token'];state['owner_token']=owner;save()
        check('Owner password authentication',bool(owner))
        pin={'company_id':company,'branch_id':branch,'shop_id':reg['shop']['id'],'device_id':reg['device']['id'],'device_key':reg['device']['device_key'],'pin':'4321'}
        if state.get('pin_session'):pin['session_token']=state['pin_session']['access_token']
        session=call('POST','/employees/pin-login',data=pin).json();state['pin_session']=session;save();token=session['access_token']
        check('Cashier PIN and registered device authentication',session['id']==reg['employee']['id'])
        if not state.get('product'):
            state['product']=call('POST','/products',token=owner,data={'company_id':company,'branch_id':branch,'create_request_key':'phase7f-synthetic-product-1',
                'name':'Acceptance Stock Product','sku':'STAGE7F-001','cost_price':'4.00','selling_price':'10.00','stock_qty':'100','reorder_level':'5'}).json();save()
        product=state['product']['id']
        products=call('GET',f'/products/{company}?branch_id={branch}',token=token).json()
        check('POS and Backoffice share product API',any(row['id']==product for row in products))
        if not state.get('shift'):
            state['shift']=call('POST','/shifts/open',token=token,data={'idempotency_key':'phase7f-shift-1','opening_balances':[{'currency_code':'USD','amount':'10'}]}).json();save()
        shift=state['shift']['id']
        if not state.get('sale_payload'):
            state['sale_payload']={'company_id':company,'branch_id':branch,'employee_id':session['id'],'device_id':reg['device']['id'],
                'device_key':reg['device']['device_key'],'shift_id':shift,'payment_method':'cash','amount_received':'20.00',
                'client_sale_id':str(uuid.uuid4()),
                'items':[{'product_id':product,'quantity':'2','unit_price':'10.00'}]};save()
        # The first rehearsal fixture was rejected with HTTP 409 before commit.
        # Retain it for evidence; it is not an offline POS queue record.
        if 'client_created_at' in state['sale_payload']:
            state['rejected_fixture']=state['sale_payload']
            state['sale_payload']={k:v for k,v in state['rejected_fixture'].items() if k!='client_created_at'}
            state['sale_payload']['client_sale_id']=str(uuid.uuid4());save()
        sale=call('POST','/sales',token=token,data=state['sale_payload']).json()
        retry=call('POST','/sales',token=token,data=state['sale_payload']).json()
        state['sale_id']=sale['id'];save()
        check('Cash sale and retry return same transaction',sale['id']==retry['id'])
        stock=call('GET',f'/inventory/branch-overview/{company}?branch_id={branch}',token=owner).json()
        check('Online retry does not add stock deductions',Decimal(next(r['quantity'] for r in stock if r['product_id']==product)) in {Decimal('98'),Decimal('97')})
        if not state.get('offline_payload'):
            state['offline_payload']={**state['sale_payload'],'client_sale_id':str(uuid.uuid4()),
                'client_created_at':datetime.now(timezone.utc).isoformat(),'offline_shift_token':state['shift']['offline_shift_token'],
                'amount_received':'10.00','items':[{'product_id':product,'quantity':'1','unit_price':'10.00'}]};save()
        offline=call('POST','/sales',token=token,data=state['offline_payload']).json()
        offline_retry=call('POST','/sales',token=token,data=state['offline_payload']).json()
        check('Cashier-bound offline synchronization is idempotent',offline['id']==offline_retry['id'] and offline['shift_id']==shift)
        stock=call('GET',f'/inventory/branch-overview/{company}?branch_id={branch}',token=owner).json()
        check('Offline retry stock deducted once',Decimal(next(r['quantity'] for r in stock if r['product_id']==product))==Decimal('97'))
        today=datetime.now(timezone.utc).date().isoformat()
        history=call('GET',f'/reports/sales-history/{company}?date_from={today}&date_to={today}',token=owner).json()
        check('Backoffice sales history contains completed POS sale',sale['id'] in json.dumps(history))
        inventory=call('GET',f'/reports/inventory-valuation/{company}?branch_id={branch}',token=owner)
        check('Backoffice inventory valuation API',inventory.status_code==200)
        closed=call('POST',f'/shifts/{shift}/close',token=token,data={'confirmed':True,'idempotency_key':'phase7f-close-1','counted_balances':[{'currency_code':'USD','amount':'40'}]}).json()
        check('Shift closes and reconciles synthetic cash',closed['status']=='closed' and Decimal(closed['currencies'][0]['expected_cash'])==Decimal('40'))
        pdf=call('GET',f'/shifts/{shift}/z-report.pdf',token=token)
        check('Immutable Z Report PDF',pdf.content.startswith(b'%PDF'))
        for width in (58,80):
            thermal=call('GET',f'/shifts/{shift}/z-report/thermal?paper_width={width}mm',token=token)
            check(f'{width}mm thermal report generation',thermal.status_code==200 and '<html' in thermal.text.lower())
        call('GET',f'/products/{other["registration"]["company"]["id"]}',token=owner,expected=403)
        check('Cross-company catalog isolation',True)
        if not state.get('second_branch'):
            state['second_branch']=call('POST','/inventory/branches',token=owner,data={'company_id':company,'shop_id':reg['shop']['id'],'name':'Synthetic Branch B'}).json();save()
        if not state.get('cashier'):
            state['cashier']=call('POST','/employees',token=owner,data={'company_id':company,'shop_id':reg['shop']['id'],'branch_id':branch,'name':'Restricted Acceptance Cashier','pin':'9753','role':'cashier','permissions':{'sales':True}}).json();save()
        call('POST','/employees/session/logout',token=token)
        limited=call('POST','/employees/pin-login',data={**pin,'pin':'9753','session_token':None}).json();limited_token=limited['access_token']
        call('GET',f'/employees/{company}',token=limited_token,expected=403)
        check('Cashier cannot manage employees',True)
        call('GET',f'/inventory/branch-overview/{company}?branch_id={state["second_branch"]["id"]}',token=limited_token,expected=403)
        check('Cross-branch inventory isolation',True)
        call('POST','/employees/session/logout',token=limited_token)
        state.pop('pin_session',None);save()
    print(json.dumps({'checks_passed':len(checks),'synthetic_only':True,'database':'apexretail_phase7f_acceptance'}))

if __name__=='__main__':main()
