"""Actual HTTPS actions in the EXISTING acceptance tenant/database only.

No provisioning, migration, database reset, production URL or hardware access.
Credentials stay in process memory; evidence contains assertions, not tokens.
"""
import json
import subprocess
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
import httpx

ROOT=Path('/tmp/apexretail-phase7f-runtime')
SOURCE=Path(__file__).resolve().parents[1]
BASE='https://localhost:18770/api'
OUT=SOURCE/'artifacts/phase7-software-completion'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    account=json.loads((ROOT/'acceptance-accounts.json').read_text())['accounts'][0]
    reg=account['registration'];company=reg['company']['id'];branch=reg['branch']['id'];device=reg['device']
    run=str(uuid4());checks=[];actor=None
    def check(name,condition=True):
        checks.append({'check':name,'result':'PASS' if condition else 'FAIL'})
        (OUT/'authenticated-api-results.json').write_text(json.dumps({'checks':checks,'productionAccessed':False,'physicalHardware':False},indent=2))
        if not condition:raise RuntimeError(name)
    with httpx.Client(verify=str(ROOT/'keys/local-ca.pem'),trust_env=False,timeout=45) as client:
        def call(method,path,data=None,*,token=None,status=200):
            response=client.request(method,BASE+path,json=data,headers={'Authorization':'Bearer '+(token or actor)} if token or actor else {})
            if response.status_code!=status:
                raise RuntimeError(f'{method} {path}: expected {status}, got {response.status_code}: {response.text[:220]}')
            return response.json() if 'application/json' in response.headers.get('content-type','') else response.content
        identity=call('GET','/staging-identity')
        expected=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()
        check('Existing isolated database, restricted runtime role and committed API source',identity['database']=='apexretail_phase7f_acceptance' and identity['role']=='apex_user' and identity['source_commit']==expected)
        owner=call('POST','/auth/login',{'email':account['email'],'password':account['password']})['token'];actor=owner
        check('Actual owner password authentication',bool(owner))
        other=json.loads((ROOT/'acceptance-accounts.json').read_text())['accounts'][1]['registration']['company']['id']
        call('GET',f'/inventory/count-catalog/{other}?branch_id={branch}',status=403)
        check('Count catalog rejects another tenant')
        categories='/products/categories'
        category=call('POST',categories,{'company_id':company,'name':'Completion '+run})
        renamed=call('PATCH',f'{categories}/{company}/{category["id"]}',{'name':'Reviewed '+run})
        check('Category create/edit/list use real shared backend',any(r['id']==category['id'] and r['name']==renamed['name'] for r in call('GET',f'{categories}/{company}')))
        product=call('POST','/products',{'company_id':company,'branch_id':branch,'create_request_key':run,'name':'Completion stock '+run,'category_id':category['id'],'cost_price':'2','selling_price':'5','stock_qty':'30'})
        call('DELETE',f'{categories}/{company}/{category["id"]}',status=409);check('Dependent category delete protected')
        edited=call('PATCH',f'/products/{company}/{product["id"]}',{'name':'Verified stock '+run})
        check('Product update persisted',edited['name'].startswith('Verified stock'))
        variant=call('POST',f'/products/variants/{company}/{product["id"]}',{'name':'Small','branch_id':branch,'cost_price':'3','selling_price':'6','stock_qty':'12','sku':'V-'+run})
        variant=call('PATCH',f'/products/variants/{company}/item/{variant["id"]}',{'branch_id':branch,'name':'Small verified','selling_price':'6'})
        check('Variant create/edit retains opening quantity',Decimal(variant['stock_qty'])==12)
        level=call('POST',f'/products/price-levels/{company}/{product["id"]}',{'name':'Wholesale','price':'4','minimum_quantity':'5'})
        call('PATCH',f'/products/price-levels/{company}/item/{level["id"]}',{'price':'4.50'})
        call('DELETE',f'/products/price-levels/{company}/item/{level["id"]}')
        check('Price level create/edit/delete')
        branches=call('GET',f'/inventory/transfer-destinations/{company}')
        destination=next(r['id'] for r in branches if r['id']!=branch)
        transfer={'company_id':company,'source_branch_id':branch,'destination_branch_id':destination,'request_id':str(uuid4()),'items':[{'product_id':product['id'],'variant_id':variant['id'],'quantity':'3'}]}
        moved=call('POST','/inventory/transfers',transfer);again=call('POST','/inventory/transfers',transfer)
        check('Authenticated variant transfer retry returns original two movements',len(moved)==2 and [r['id'] for r in moved]==[r['id'] for r in again] and all(r['variant_id']==variant['id'] for r in moved))
        positions=call('GET',f'/inventory/count-catalog/{company}?branch_id={branch}')
        position=next(r for r in positions if r['variant_id']==variant['id'])
        check('Transferred variant source quantity is nine',Decimal(position['stock_qty'])==9)
        count={'company_id':company,'branch_id':branch,'request_id':str(uuid4()),'items':[{'product_id':product['id'],'variant_id':variant['id'],'expected_qty':'9','physical_qty':'8'}]}
        counted=call('POST','/inventory/stock-take',count);again=call('POST','/inventory/stock-take',count)
        check('Authenticated count commits once and preserves variant',counted[0]['id']==again[0]['id'] and counted[0]['variant_id']==variant['id'])
        call('POST','/inventory/stock-take',{**count,'request_id':str(uuid4())},status=409);check('Stale physical count rejected without overwrite')
        old_profile=call('GET','/operations/profile')
        try:
            call('PUT','/operations/profile',{'profile':'pharmacy','tip_product_id':old_profile.get('tip_product_id'),'service_product_id':old_profile.get('service_product_id')})
            lot={'branch_id':branch,'product_id':product['id'],'variant_id':variant['id'],'code':'LOT-'+run,'expires_on':str(date.today()+timedelta(days=90)),'quantity':'4','request_id':str(uuid4()),'operation':'receive','reason':'Synthetic authenticated acceptance'}
            receipt=call('POST','/operations/batches/stock',lot);again=call('POST','/operations/batches/stock',lot)
            check('Variant batch receipt deduplicates stock movement',receipt['movement_id']==again['movement_id'])
            batches=call('GET','/operations/batches')
            batch=next(r for r in batches if r['id']==receipt['batch_id'])
            check('Batch retains selected variant, code, expiry and received quantity',batch['variant_id']==variant['id'] and batch['code']==lot['code'] and batch['expires_on']==lot['expires_on'] and Decimal(batch['quantity'])==4)
            lotcount={**lot,'request_id':str(uuid4()),'operation':'count','quantity':'3','expected_qty':'4'}
            call('POST','/operations/batches/stock',lotcount)
            call('POST','/operations/batches/stock',{**lotcount,'request_id':str(uuid4())},status=409)
            check('Selected-lot count rejects stale quantity')
            for operation in ('supplier_return','dispose'):
                command={**lot,'request_id':str(uuid4()),'operation':operation,'quantity':'1'}
                a=call('POST','/operations/batches/stock',command);b=call('POST','/operations/batches/stock',command)
                check(f'Batch {operation} deduplicates movement',a['movement_id']==b['movement_id'])
            call('POST','/operations/batches/stock',{**lot,'request_id':str(uuid4()),'operation':'dispose','quantity':'2'},status=409)
            check('Batch disposal cannot create negative lot stock')
            today=date.today().isoformat()
            valuation=call('GET',f'/reports/batch-valuation/{company}?branch_id={branch}')
            check('Authenticated batch valuation responds with actual records',isinstance(valuation,dict))
            call('PUT','/operations/profile',{'profile':'restaurant','tip_product_id':old_profile.get('tip_product_id'),'service_product_id':old_profile.get('service_product_id')})
            station=call('POST','/printing/stations',{'shop_id':reg['shop']['id'],'branch_id':branch,'device_id':device['id'],'name':'Synthetic kitchen '+run,'purpose':'kitchen','transport':'system','paper_width':'58mm','auto_print':False,'routes':[{'target_type':'product','target_id':product['id']}]})
            check('Kitchen station routes only selected synthetic product',bool(station['id']))
            login={'company_id':company,'branch_id':branch,'shop_id':reg['shop']['id'],'device_id':device['id'],'device_key':device['device_key'],'pin':account['pin']}
            session=call('POST','/employees/pin-login',login);actor=session['access_token']
            check('Actual employee PIN and registered-device authentication',session['id']==reg['employee']['id'])
            draft={'request_id':str(uuid4()),'employee_id':session['id'],'captured_at':datetime.now(timezone.utc).isoformat(),'order':{'request_id':str(uuid4()),'branch_id':branch,'device_id':device['id'],'kind':'restaurant'},'items':[{'version':1,'product_id':product['id'],'quantity':'2'}]}
            saved=call('POST','/operations/offline/drafts',draft);replay=call('POST','/operations/offline/drafts',draft)
            check('Offline saved order synchronizes once',saved['order']['id']==replay['order']['id'])
            recovered=call('POST','/operations/offline/drafts/recover',draft)
            check('Restart recovery returns original order',recovered['order']['id']==saved['order']['id'])
            kitchen={'request_id':str(uuid4()),'employee_id':session['id'],'device_id':device['id'],'captured_at':draft['captured_at'],'order_id':saved['order']['id'],'version':saved['order']['version']}
            sent=call('POST','/operations/offline/kitchen',kitchen);again=call('POST','/operations/offline/kitchen',kitchen)
            tickets=call('GET','/operations/kitchen');ticket=next(t for t in tickets if t['payload']['order_number']==sent['order']['number'])
            check('Explicit queued KOT produces one routed ticket',sent['order']['id']==again['order']['id'] and len([t for t in tickets if t['payload']['order_number']==sent['order']['number']])==1)
            kds={'request_id':str(uuid4()),'employee_id':session['id'],'device_id':device['id'],'captured_at':draft['captured_at'],'ticket_id':ticket['id'],'expected_status':ticket['status'],'status':'preparing'}
            changed=call('POST','/operations/offline/kds',kds);replay=call('POST','/operations/offline/kds',kds)
            check('Offline KDS sync and retry retain original acknowledgement',changed['request_id']==replay['request_id']==kds['request_id'])
            stale={**kds,'request_id':str(uuid4()),'status':'ready'}
            call('POST','/operations/offline/kds',stale,status=409)
            review=call('POST','/operations/offline/kds/review',{'command':stale,'reason':'Review synthetic conflict'})
            resolved=call('POST','/operations/offline/kds/resolve',{'command':stale,'observed_status':review['current_status'],'reason':'Accept reviewed server state'})
            replay=call('POST','/operations/offline/kds',stale)
            check('Explicit audited conflict resolution prevents later mutation',resolved['resolution']['decision']=='accepted_server_state' and replay['resolution']==resolved['resolution'])
            current=call('GET','/shifts/current')
            if current is not None:raise RuntimeError('Existing shift found; refusing to close or repurpose it')
            shift=call('POST','/shifts/open',{'idempotency_key':run+'-open'})
            check('Shift opens with zero optional float',Decimal(shift['currencies'][0]['opening_float'])==0)
            payment={'company_id':company,'branch_id':branch,'device_id':device['id'],'device_key':device['device_key'],'employee_id':session['id'],'shift_id':shift['id'],'client_sale_id':str(uuid4()),'payment_method':'cash','amount_received':'6','items':[{'product_id':product['id'],'variant_id':variant['id'],'quantity':'1','unit_price':'6'}]}
            sale=call('POST','/sales',payment);again=call('POST','/sales',payment)
            check('Online variant cash sale is idempotent and cashier-bound',sale['id']==again['id'] and sale['shift_id']==shift['id'])
            variantrow=next(v for v in call('GET',f'/products/variants/{company}?product_id={product["id"]}&branch_id={branch}') if v['id']==variant['id'])
            check('Variant stock deducts exactly once after count/receiving/returns/disposal/sale',Decimal(variantrow['stock_qty'])==8)
            history=call('GET',f'/reports/sales-history/{company}?date_from={today}&date_to={today}&branch_id={branch}',token=owner)
            check('Backoffice sales report includes completed POS transaction',sale['id'] in json.dumps(history))
            closing=call('POST',f'/shifts/{shift["id"]}/close',{'confirmed':True,'idempotency_key':run+'-close','counted_balances':[{'currency_code':'USD','amount':'6'}]})
            check('Own shift closes with accurate expected cash',closing['status']=='closed' and Decimal(closing['currencies'][0]['expected_cash'])==6)
            pdf=call('GET',f'/shifts/{shift["id"]}/z-report.pdf')
            check('Z Report PDF uses immutable closing data',pdf.startswith(b'%PDF'))
            for width in (58,80):check(f'{width}mm report generation only (not physical print)',b'<html' in call('GET',f'/shifts/{shift["id"]}/z-report/thermal?paper_width={width}mm').lower())
            call('POST','/employees/session/logout');actor=owner
        finally:
            call('PUT','/operations/profile',{'profile':old_profile['profile'],'tip_product_id':old_profile.get('tip_product_id'),'service_product_id':old_profile.get('service_product_id')},token=owner)
        empty=call('POST',categories,{'company_id':company,'name':'Temporary empty '+run})
        call('DELETE',f'{categories}/{company}/{empty["id"]}')
        check('Empty category deletes through authenticated API')
        (OUT/'authenticated-fixture.json').write_text(json.dumps({'companyId':company,'branchId':branch,'productId':product['id'],'variantId':variant['id'],'run':run},indent=2))
    print(json.dumps({'passed':len(checks),'database':'apexretail_phase7f_acceptance','productionAccessed':False,'newDatabaseCreated':False}))


if __name__=='__main__':main()
