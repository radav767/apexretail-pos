"""Tenant-scoped presentation defaults never alter operational settings."""
import unittest
from uuid import uuid4,UUID
from unittest.mock import patch
from sqlalchemy import select,func
from app.models import WorkflowCommand,WorkflowRecord,CompanySetting,CompanySubscription,Branch,User,InventoryBalance,InventoryMovement
from app.auth.security import create_employee_access_token
import test_phase11_procurement as fixtures

class PresentationPreferenceTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.ProcurementTests.cleanup
    asyncSetUp=fixtures.ProcurementTests.asyncSetUp
    async def put(self,scope='company',version=0,values=None,status=200,**fields):
        body={'company_id':str(self.c),'request_id':str(uuid4()),'scope':scope,'version':version,'preferences':values if values is not None else {'selector_view':'cards'},**fields}
        response=await self.client.put(f'/api/settings/preferences/{self.c}',json=body)
        self.assertEqual(response.status_code,status,response.text);return (response.json() if response.headers.get('content-type','').startswith('application/json') else {}),body
    async def read(self,**params):
        response=await self.client.get(f'/api/settings/preferences/{self.c}',params=params);self.assertEqual(response.status_code,200,response.text);return response.json()
    async def test_precedence_clear_scopes_and_current_device_revision(self):
        self.assertEqual((await self.read())['effective'],{'selector_view':'table','tool_color_scheme':'light'})
        company,_=await self.put()
        self.assertEqual((await self.read(branch_id=str(self.b)))['sources']['selector_view'],'company')
        branch,_=await self.put('branch',branch_id=str(self.b),values={'selector_view':'table'})
        device,_=await self.put('device',branch_id=str(self.b),device_id=str(self.device.id))
        value=await self.read(branch_id=str(self.b),device_id=str(self.device.id));self.assertEqual(value['effective']['selector_view'],'cards');self.assertEqual(value['sources']['selector_view'],'device')
        await self.put('device',version=1,branch_id=str(self.b),device_id=str(self.device.id),values={})
        value=await self.read(branch_id=str(self.b),device_id=str(self.device.id));self.assertEqual(value['effective']['selector_view'],'table');self.assertEqual(value['sources']['selector_view'],'branch')
        await self.put('branch',version=1,branch_id=str(self.b),values={})
        self.assertEqual((await self.read(branch_id=str(self.b)))['sources']['selector_view'],'company')
        self.device.assignment_revision+=1;await self.db.commit()
        value=await self.read(branch_id=str(self.b),device_id=str(self.device.id));self.assertEqual(value['scopes'][-1]['version'],0)
        settings=(await self.db.execute(select(CompanySetting).where(CompanySetting.company_id==self.c))).scalar_one();self.assertEqual(settings.currency_code,'USD');self.assertEqual(settings.tax_rate,0)
        self.assertEqual((await self.db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==self.c,InventoryBalance.product_id==self.p))).scalar_one(),100)
        self.assertEqual((await self.db.execute(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.company_id==self.c))).scalar_one(),0)
    async def test_exact_replay_stale_writes_expiry_and_rollback(self):
        saved,body=await self.put()
        response=await self.client.put(f'/api/settings/preferences/{self.c}',json=body);self.assertEqual(response.json(),saved)
        await self.put(status=409)
        changed={**body,'preferences':{'selector_view':'table'}};self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json=changed)).status_code,409)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit()
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json=body)).json(),saved)
        await self.put(version=1,status=402)
        self.assertEqual((await self.read())['effective']['selector_view'],'cards')
    async def test_tenant_role_branch_device_and_unknown_keys_fail_closed(self):
        self.assertEqual((await self.client.get(f'/api/settings/preferences/{uuid4()}')).status_code,403)
        await self.put('branch',branch_id=str(uuid4()),status=404)
        await self.put('company',branch_id=str(self.b),status=422)
        await self.put(values={'posting_enabled':True},status=422)
        await self.put(values={'selector_view':'html'},status=422)
        token=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='cashier')
        _,body=await self.put()
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json={**body,'request_id':str(uuid4())},headers={'Authorization':'Bearer '+token})).status_code,403)
        self.employee.permissions={**self.employee.permissions,'business_settings_manage':True};await self.db.commit()
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json={**body,'request_id':str(uuid4()),'version':1},headers={'Authorization':'Bearer '+token})).status_code,403)
        response=await self.client.get(f'/api/settings/preferences/{self.c}',headers={'Authorization':'Bearer '+token});self.assertEqual(response.status_code,200);self.assertEqual(response.json()['branch_id'],str(self.b))
        branch_body={**body,'request_id':str(uuid4()),'scope':'branch','branch_id':str(self.b)}
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json=branch_body,headers={'Authorization':'Bearer '+token})).status_code,200)
        device_body={**body,'request_id':str(uuid4()),'scope':'device','branch_id':str(self.b),'device_id':str(self.device.id)}
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json=device_body,headers={'Authorization':'Bearer '+token})).status_code,403)
        other=Branch(company_id=self.c,shop_id=self.shop.id,name='Synthetic foreign branch');self.db.add(other);await self.db.commit()
        self.assertEqual((await self.client.get(f'/api/settings/preferences/{self.c}',params={'branch_id':str(other.id)},headers={'Authorization':'Bearer '+token})).status_code,403)
        user=await self.db.get(User,self.u);user.session_version+=1;await self.db.commit();self.assertEqual((await self.client.get(f'/api/settings/preferences/{self.c}')).status_code,401)
    async def test_command_failure_rolls_back_projection_and_acknowledgement(self):
        from app.workflows.core import WorkflowService
        async def fail(svc,*args,**kwargs):
            await svc.db.flush();raise RuntimeError('Synthetic preference projection failure')
        with patch.object(WorkflowService,'finish',fail):await self.put(status=500)
        # Request transaction cleanup is explicit in this shared rollback fixture.
        await self.db.rollback()
        self.assertEqual((await self.read())['effective']['selector_view'],'table')
        await self.put()

    async def test_v2_colour_precedence_preserves_legacy_fingerprints_acknowledgements_and_owned_keys(self):
        from app.sales.commands import fingerprint
        from app.business_settings.preferences import SavePreferences
        original,legacy=await self.put()
        old_hash=fingerprint(SavePreferences(**legacy))
        async def v2(scope,version,values,**fields):
            body={'contract_version':'presentation-preferences-v2','company_id':str(self.c),'request_id':str(uuid4()),'scope':scope,'version':version,'preferences':values,**fields}
            response=await self.client.put(f'/api/settings/preferences/{self.c}',json=body);self.assertEqual(response.status_code,200,response.text);return response.json(),body
        saved,body=await v2('company',1,{'selector_view':'cards','tool_color_scheme':'dark'})
        self.assertEqual((await self.read())['effective'],{'selector_view':'cards','tool_color_scheme':'dark'})
        replay=await self.client.put(f'/api/settings/preferences/{self.c}',json=legacy);self.assertEqual(replay.json(),original)
        self.assertEqual((await self.db.get(WorkflowCommand,UUID(legacy['request_id']))).payload_hash,old_hash)
        # Legacy calls continue to own only selector_view, not newer overrides.
        await self.put(version=2,values={'selector_view':'table'})
        self.assertEqual((await self.read())['effective'],{'selector_view':'table','tool_color_scheme':'dark'})
        await v2('branch',0,{'tool_color_scheme':'system'},branch_id=str(self.b))
        result=await self.read(branch_id=str(self.b));self.assertEqual(result['effective']['tool_color_scheme'],'system');self.assertEqual(result['sources']['tool_color_scheme'],'branch');self.assertEqual(result['sources']['selector_view'],'company')
        await v2('device',0,{'tool_color_scheme':'light'},branch_id=str(self.b),device_id=str(self.device.id))
        result=await self.read(branch_id=str(self.b),device_id=str(self.device.id));self.assertEqual(result['effective']['tool_color_scheme'],'light');self.assertEqual(result['sources']['tool_color_scheme'],'device')
        await v2('device',1,{},branch_id=str(self.b),device_id=str(self.device.id))
        self.assertEqual((await self.read(branch_id=str(self.b),device_id=str(self.device.id)))['effective']['tool_color_scheme'],'system')
        await v2('company',3,{})
        self.assertEqual((await self.read())['effective'],{'selector_view':'table','tool_color_scheme':'light'})
        bad={**body,'request_id':str(uuid4()),'version':4,'preferences':{'tool_color_scheme':'url(https://provider.invalid)'}}
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json=bad)).status_code,422)
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json={**legacy,'preferences':{'tool_color_scheme':'dark'}})).status_code,422)

    async def test_v3_backoffice_workspace_inheritance_and_mixed_legacy_ownership(self):
        from app.business_settings.preferences import SavePreferences,SaveAppearance
        from app.sales.commands import fingerprint
        contract='backoffice-workspace-preferences-v3'
        async def send(scope,version,values,status=200,**fields):
            body={'contract_version':contract,'company_id':str(self.c),'request_id':str(uuid4()),'scope':scope,'version':version,'preferences':values,**fields}
            response=await self.client.put(f'/api/settings/preferences/{self.c}',json=body);self.assertEqual(response.status_code,status,response.text);return response.json(),body
        old,v1=await self.put()
        v2={**v1,'request_id':str(uuid4()),'version':1,'contract_version':'presentation-preferences-v2','preferences':{'tool_color_scheme':'dark'}}
        second=await self.client.put(f'/api/settings/preferences/{self.c}',json=v2);self.assertEqual(second.status_code,200,second.text)
        before_hashes=[fingerprint(SavePreferences(**v1)),fingerprint(SaveAppearance(**v2))]
        saved,body=await send('company',2,{'selector_view':'cards','tool_color_scheme':'dark','backoffice_workspace_view':'list','backoffice_text_size':'large'})
        metadata=await self.read();self.assertEqual(metadata['contract_version'],'presentation-preferences-v2');self.assertEqual(metadata['capabilities']['workspace_preferences'],contract)
        for original,ack,original_hash in [(v1,old,before_hashes[0]),(v2,second.json(),before_hashes[1])]:
            self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json=original)).json(),ack)
            self.assertEqual((await self.db.get(WorkflowCommand,UUID(original['request_id']))).payload_hash,original_hash)
        await self.put(version=3,values={})
        self.assertEqual((await self.read())['effective'],{'selector_view':'table','tool_color_scheme':'dark','backoffice_workspace_view':'list','backoffice_text_size':'large'})
        clear_v2={**v2,'request_id':str(uuid4()),'version':4,'preferences':{}}
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json=clear_v2)).status_code,200)
        self.assertEqual((await self.read())['effective'],{'selector_view':'table','tool_color_scheme':'light','backoffice_workspace_view':'list','backoffice_text_size':'large'})
        await send('branch',0,{'backoffice_text_size':'standard'},branch_id=str(self.b))
        await send('device',0,{'backoffice_workspace_view':'tiles'},branch_id=str(self.b),device_id=str(self.device.id))
        result=await self.read(branch_id=str(self.b),device_id=str(self.device.id));self.assertEqual(result['effective']['backoffice_text_size'],'standard');self.assertEqual(result['sources']['backoffice_text_size'],'branch');self.assertEqual(result['sources']['backoffice_workspace_view'],'device')
        await send('device',1,{},branch_id=str(self.b),device_id=str(self.device.id))
        self.assertEqual((await self.read(branch_id=str(self.b),device_id=str(self.device.id)))['sources']['backoffice_workspace_view'],'company')
        await send('device',2,{'backoffice_workspace_view':'tiles'},branch_id=str(self.b),device_id=str(self.device.id))
        self.device.assignment_revision+=1;await self.db.commit()
        result=await self.read(branch_id=str(self.b),device_id=str(self.device.id));self.assertEqual(result['scopes'][-1]['version'],0);self.assertEqual(result['sources']['backoffice_workspace_view'],'company')
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json=body)).json(),saved)
        await send('company',2,{},status=409)
        for invalid in [{'backoffice_text_size':'url(https://provider.invalid)'},{'backoffice_workspace_view':'recipes'},{'posting_enabled':True}]:
            await send('company',5,invalid,status=422)
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json={**v2,'preferences':{'backoffice_text_size':'large'}})).status_code,422)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.c))).scalar_one();sub.status='expired';await self.db.commit()
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json=body)).json(),saved)
        await send('company',5,{},status=402)
        user=await self.db.get(User,self.u);user.session_version+=1;await self.db.commit()
        self.assertEqual((await self.client.put(f'/api/settings/preferences/{self.c}',json=body)).status_code,401)
        self.assertEqual((await self.db.execute(select(InventoryBalance.quantity).where(InventoryBalance.company_id==self.c,InventoryBalance.product_id==self.p))).scalar_one(),100)
        self.assertEqual((await self.db.execute(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.company_id==self.c))).scalar_one(),0)

    async def test_v3_failure_rolls_back_and_employee_cannot_set_company_workspace(self):
        from app.workflows.core import WorkflowService
        body={'contract_version':'backoffice-workspace-preferences-v3','company_id':str(self.c),'request_id':str(uuid4()),'scope':'company','version':0,'preferences':{'backoffice_workspace_view':'list','backoffice_text_size':'large'}}
        token=create_employee_access_token(employee_id=str(self.e),company_id=str(self.c),role='cashier')
        response=await self.client.put(f'/api/settings/preferences/{self.c}',json=body,headers={'Authorization':'Bearer '+token});self.assertEqual(response.status_code,403,response.text)
        async def fail(svc,*args,**kwargs):await svc.db.flush();raise RuntimeError('Synthetic workspace acknowledgement failure')
        with patch.object(WorkflowService,'finish',fail):
            response=await self.client.put(f'/api/settings/preferences/{self.c}',json=body);self.assertEqual(response.status_code,500,response.text)
        await self.db.rollback()
        self.assertNotIn('backoffice_workspace_view',(await self.read())['effective'])
        self.assertIsNone(await self.db.get(WorkflowCommand,UUID(body['request_id'])))
        response=await self.client.put(f'/api/settings/preferences/{self.c}',json=body);self.assertEqual(response.status_code,200,response.text)
