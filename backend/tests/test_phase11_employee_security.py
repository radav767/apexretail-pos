"""Security-only employee changes remain possible after expiry and revoke epochs."""
from uuid import uuid4
import unittest
from sqlalchemy import select
import httpx
from app.models import CompanySubscription, EmployeeRole, Company, User
from app.auth.security import create_access_token,create_employee_access_token,hash_session_token
from app.db.session import get_db
from app.main import app
from app.employees.service import EmployeeService
from app.employees.repository import EmployeeRepository
from app.employees.admin_service import EmployeeAdminService
from app.employees.schema import EmployeeUpdate,RoleCreate,RoleUpdate,EmployeeCreate
from app.auth.dependencies import AuthActor
import test_phase7d_operations as fixtures


class EmployeeSecurityTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.license=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one()
        self.svc=EmployeeService(EmployeeRepository(self.db));self.roles=EmployeeAdminService(self.db)
        self.opaque='synthetic-employee-security-'+str(uuid4());self.session.token_hash=hash_session_token(self.opaque)
        self.legacy=create_employee_access_token(employee_id=str(self.employee.id),company_id=str(self.company.id),role=self.employee.role)
        await self.db.commit()
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test');self.addAsyncCleanup(self.client.aclose)
        self.owner_headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)}
    async def read(self,token):return await self.client.get('/api/employees/permissions/catalog',headers={'Authorization':'Bearer '+token})
    async def update(self,**values):return await self.client.patch(f'/api/employees/{self.company.id}/{self.employee.id}',headers=self.owner_headers,json=values)
    async def test_expired_pin_reset_revokes_opaque_and_legacy_then_fresh_pin_uses_epoch(self):
        self.license.status='expired';await self.db.commit()
        result=await self.update(pin='5678');self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.employee.session_version,1)
        for token in (self.opaque,self.legacy):self.assertEqual((await self.read(token)).status_code,401)
        old=await self.client.post('/api/employees/pin-login',json={'company_id':str(self.company.id),'branch_id':str(self.branch.id),'pin':'1234'})
        self.assertEqual(old.status_code,401,old.text)
        fresh=await self.client.post('/api/employees/pin-login',json={'company_id':str(self.company.id),'branch_id':str(self.branch.id),'shop_id':str(self.shop.id),
            'device_id':str(self.device.id),'device_key':self.device.device_key,'pin':'5678'})
        self.assertEqual(fresh.status_code,200,fresh.text);self.assertEqual((await self.read(fresh.json()['access_token'])).status_code,200)
    async def test_expired_access_reduction_allowed_but_new_grants_and_cosmetics_fail_without_mutation(self):
        self.license.status='expired';await self.db.commit()
        original_name=self.employee.name
        denied=await self.update(name='Unlicensed change');self.assertEqual(denied.status_code,402,denied.text);self.assertEqual(self.employee.name,original_name)
        denied=await self.update(permissions={'sales_refund':True});self.assertEqual(denied.status_code,402,denied.text)
        reduced=await self.update(permissions={'sales_process':False});self.assertEqual(reduced.status_code,200,reduced.text)
        self.assertEqual(self.employee.session_version,1)
        for token in (self.opaque,self.legacy):self.assertEqual((await self.read(token)).status_code,401)
        denied=await self.update(permissions={'sales_process':True});self.assertEqual(denied.status_code,402,denied.text)
        self.assertFalse((await EmployeeService.effective_permissions(self.employee,self.db))['sales_process'])
    async def test_deactivation_and_deletion_remain_available_but_reactivation_requires_license(self):
        self.license.status='expired';await self.db.commit()
        result=await self.update(active=False);self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.employee.session_version,1);self.assertFalse(self.employee.active)
        self.assertEqual((await self.update(active=True)).status_code,402)
        result=await self.client.delete(f'/api/employees/{self.company.id}/{self.employee.id}',headers=self.owner_headers)
        self.assertEqual(result.status_code,200,result.text);self.assertTrue(self.employee.deleted);self.assertEqual(self.employee.session_version,2)
    async def test_register_access_reduction_after_expiry_revokes_sessions_and_cannot_regrant(self):
        self.license.status='expired';await self.db.commit()
        result=await self.update(device_restricted=True,device_ids=[str(self.device.id)])
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(self.employee.session_version,1)
        self.assertEqual(set(await self.svc.repo.device_ids(self.employee.id)),{self.device.id})
        reduced=await self.update(device_ids=[]);self.assertEqual(reduced.status_code,200,reduced.text)
        self.assertEqual(self.employee.session_version,2)
        denied=await self.update(device_ids=[str(self.device.id)]);self.assertEqual(denied.status_code,402,denied.text)
        self.assertEqual(await self.svc.repo.device_ids(self.employee.id),[])
        denied=await self.update(device_restricted=False);self.assertEqual(denied.status_code,402,denied.text)

    async def test_shared_role_permission_reduction_revokes_assigned_employees_after_expiry(self):
        role=await self.roles.create_role(RoleCreate(company_id=self.company.id,name='Synthetic counter',permissions={'sales_process':True}),self.owner)
        await self.svc.update(self.company.id,self.employee.id,EmployeeUpdate(role_id=role['id']),self.owner)
        before=self.employee.session_version
        current=create_employee_access_token(employee_id=str(self.employee.id),company_id=str(self.company.id),role='custom',session_version=before)
        self.assertEqual((await self.read(current)).status_code,200)
        self.license.status='expired';await self.db.commit()
        updated=await self.roles.update_role(self.company.id,role['id'],RoleUpdate(permissions={'sales_process':False}),self.owner)
        self.assertFalse(updated['permissions']['sales_process']);self.assertEqual(self.employee.session_version,before+1)
        self.assertEqual((await self.read(current)).status_code,401)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as error:await self.roles.update_role(self.company.id,role['id'],RoleUpdate(permissions={'sales_process':True}),self.owner)
        self.assertEqual(error.exception.status_code,402)
    async def test_direct_tenant_and_actor_checks_precede_role_or_employee_mutations(self):
        company=Company(name='Synthetic foreign authority',owner_email=f'{uuid4()}@example.test');self.db.add(company);await self.db.flush()
        user=User(company_id=company.id,email=f'{uuid4()}@example.test',password_hash='unused',role='owner');self.db.add(user);await self.db.commit()
        other=AuthActor(actor_type='user',company_id=company.id,role='owner',user=user)
        from fastapi import HTTPException
        for operation in [self.svc.update(self.company.id,self.employee.id,EmployeeUpdate(pin='5678'),other),
                          self.roles.create_role(RoleCreate(company_id=self.company.id,name='Foreign attempted role',permissions={}),other),
                          self.svc.delete(self.company.id,self.employee.id,other)]:
            with self.assertRaises(HTTPException) as error:await operation
            self.assertEqual(error.exception.status_code,403)
        with self.assertRaises(HTTPException) as error:await self.svc.update(self.company.id,self.employee.id,EmployeeUpdate(pin='5678'))
        self.assertEqual(error.exception.status_code,401);self.assertEqual(self.employee.session_version,0)
