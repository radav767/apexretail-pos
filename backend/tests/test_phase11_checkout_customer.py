"""Identified safe contact creation cannot grant credit, sell, or duplicate effects."""
from uuid import uuid4
import unittest
from unittest.mock import patch
import httpx
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from fastapi import HTTPException
from app.models import Customer,CheckoutCustomerCommand,CompanySubscription,Sale,InventoryMovement
from app.customers.service import CustomerService
from app.customers.repository import CustomerRepository
from app.customers.schema import CheckoutCustomerCreate
from app.auth.security import create_access_token,create_employee_access_token
from app.auth.dependencies import AuthActor
from app.db.session import get_db
from app.main import app
import test_phase7d_operations as fixtures

class CheckoutCustomerTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.svc=CustomerService(CustomerRepository(self.db));self.body={'company_id':str(self.company.id),'request_id':str(uuid4()),'name':'Synthetic inline contact','phone':'000000000','email':'synthetic@example.test','address':'Synthetic address'}
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.headers={'Authorization':'Bearer '+create_employee_access_token(employee_id=str(self.employee.id),company_id=str(self.company.id),role='cashier')}
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test',headers=self.headers);self.addAsyncCleanup(self.client.aclose)
    async def counts(self):return {m.__tablename__:(await self.db.execute(select(func.count()).select_from(m).where(m.company_id==self.company.id))).scalar_one() for m in (Customer,CheckoutCustomerCommand,Sale,InventoryMovement)}
    async def test_cashier_basic_create_exact_expired_replay_and_payload_conflict(self):
        before=await self.counts();response=await self.client.post('/api/customers/checkout',json=self.body)
        self.assertEqual(response.status_code,200,response.text);result=response.json()
        self.assertEqual(result['customer_code'],'POS-'+self.body['request_id'].replace('-','').upper());self.assertFalse(result['credit_enabled']);self.assertFalse(result['unlimited_credit']);self.assertIsNone(result['credit_limit']);self.assertIsNone(result['price_level_name'])
        self.assertEqual(self.balance.quantity,100)
        license=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one();license.status='expired';await self.db.commit()
        again=await self.client.post('/api/customers/checkout',json=self.body);self.assertEqual(again.status_code,200,again.text);self.assertEqual(again.json()['id'],result['id'])
        conflict=await self.client.post('/api/customers/checkout',json={**self.body,'name':'Changed command'});self.assertEqual(conflict.status_code,409,conflict.text)
        denied=await self.client.post('/api/customers/checkout',json={**self.body,'request_id':str(uuid4())});self.assertEqual(denied.status_code,402,denied.text)
        after=await self.counts();self.assertEqual(after['customers'],before['customers']+1);self.assertEqual(after['sales'],before['sales']);self.assertEqual(after['inventory_movements'],before['inventory_movements']);self.assertEqual(after['checkout_customer_commands'],1)
    async def test_extra_credit_fields_other_actor_and_foreign_tenant_denied(self):
        for fields in [{'credit_enabled':True},{'unlimited_credit':True},{'credit_limit':'100'},{'price_level_name':'Wholesale'},{'active':False}]:
            response=await self.client.post('/api/customers/checkout',json={**self.body,**fields});self.assertEqual(response.status_code,422,response.text)
        created=await self.client.post('/api/customers/checkout',json=self.body);self.assertEqual(created.status_code,200,created.text)
        owner={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)}
        response=await self.client.post('/api/customers/checkout',json=self.body,headers=owner);self.assertEqual(response.status_code,403,response.text)
        response=await self.client.post('/api/customers/checkout',json={**self.body,'company_id':str(uuid4())});self.assertEqual(response.status_code,403,response.text)
        self.employee.session_version+=1;await self.db.commit()
        revoked=await self.client.post('/api/customers/checkout',json=self.body);self.assertEqual(revoked.status_code,401,revoked.text)
    async def test_command_immutable_and_failure_rolls_back_new_contact_and_proof(self):
        data=CheckoutCustomerCreate(**self.body);request_id=data.request_id;company_id=self.company.id
        with patch.object(self.svc.repo,'save',side_effect=RuntimeError('synthetic contact save failure')):
            with self.assertRaises(RuntimeError):await self.svc.create_checkout(data,self.owner)
        await self.db.rollback();self.assertIsNone(await self.db.get(CheckoutCustomerCommand,request_id))
        self.assertEqual((await self.db.execute(select(func.count(Customer.id)).where(Customer.company_id==company_id))).scalar_one(),0)
        await self.db.refresh(self.user);created=await self.svc.create_checkout(data,self.owner)
        with self.assertRaises(DBAPIError):
            async with self.db.begin_nested():await self.db.execute(text('DELETE FROM checkout_customer_commands WHERE request_id=:id'),{'id':request_id})
