"""Bounded searchable catalog read model; no stock or financial mutation."""
from decimal import Decimal
from uuid import uuid4
import unittest
import httpx
from sqlalchemy import select,func
from app.models import Product,CompanySubscription,VariantInventoryBalance,ProductVariant,Branch,Category
from app.auth.security import create_access_token,create_employee_access_token
from app.db.session import get_db
from app.main import app
import test_phase7d_operations as fixtures

class ProductSelectionTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.product.sku='SKU_%literal';self.product.barcode='SCAN-EXACT';self.product.cost_price=99
        self.db.add_all([Product(company_id=self.company.id,name=f'Synthetic selection {n:04}',sku=f'FIND-{n:04}',selling_price=Decimal('12.34'),category_id=self.category.id) for n in range(270)])
        self.db.add(Product(company_id=self.company.id,name='Synthetic selection archived',active=False))
        self.db.add(Product(company_id=self.company.id,name='Synthetic selection deleted',deleted=True))
        await self.db.commit()
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test',headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)})
        self.addAsyncCleanup(self.client.aclose)
    async def get(self,**params):return await self.client.get(f'/api/products/{self.company.id}/selection',params={'branch_id':str(self.branch.id),**params})
    async def test_bounded_pages_search_barcode_literal_wildcards_and_cost_redaction(self):
        first=await self.get(search='sYnThEtIc SeLeCtIoN',page=1);second=await self.get(search='Synthetic selection',page=2)
        self.assertEqual(first.status_code,200,first.text);self.assertEqual(first.json()['total'],270);self.assertEqual(first.json()['total_pages'],11)
        self.assertEqual(len(first.json()['items']),25);self.assertTrue({r['id'] for r in first.json()['items']}.isdisjoint(r['id'] for r in second.json()['items']))
        last=await self.get(search='Synthetic selection',page=11);self.assertEqual(len(last.json()['items']),20)
        for term in ['scan-exact','SKU_%literal']:
            result=await self.get(search=term);self.assertEqual(result.status_code,200,result.text);self.assertEqual([r['id'] for r in result.json()['items']],[str(self.product.id)])
            self.assertNotIn('cost_price',result.json()['items'][0]);self.assertEqual(Decimal(result.json()['items'][0]['branch_stock_qty']),100)
        for params in [{'page_size':101},{'page':0}]:self.assertEqual((await self.get(**params)).status_code,422)
        self.assertEqual((await self.get(search='no-match')).json()['total'],0)
    async def test_branch_variant_stock_and_expired_read_scope(self):
        variant=ProductVariant(company_id=self.company.id,product_id=self.product.id,name='Synthetic size');self.db.add(variant);await self.db.flush()
        self.db.add(VariantInventoryBalance(company_id=self.company.id,shop_id=self.shop.id,branch_id=self.branch.id,product_id=self.product.id,variant_id=variant.id,quantity=7,reorder_level=0))
        license=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one();license.status='expired';license.commercial_terms={'features':{}};await self.db.commit()
        result=await self.get(search='SCAN-EXACT');self.assertEqual(result.status_code,200,result.text);self.assertEqual(Decimal(result.json()['items'][0]['branch_stock_qty']),107)
        employee=create_employee_access_token(employee_id=str(self.employee.id),company_id=str(self.company.id),role='cashier')
        other=Branch(company_id=self.company.id,shop_id=self.shop.id,name='Synthetic different branch');self.db.add(other);await self.db.commit()
        denied=await self.client.get(f'/api/products/{self.company.id}/selection',params={'branch_id':str(other.id)},headers={'Authorization':'Bearer '+employee})
        self.assertEqual(denied.status_code,403,denied.text)
        self.assertEqual((await self.client.get(f'/api/products/{uuid4()}/selection',params={'branch_id':str(self.branch.id)})).status_code,403)
        self.assertEqual((await self.get(branch_id=str(uuid4()))).status_code,404)
        self.assertEqual((await self.get(category_id=str(uuid4()))).status_code,404)

    async def test_inactive_deleted_and_foreign_selected_ids_never_become_management_reads(self):
        from app.models import InventoryMovement,Sale,Company
        from app.products.selection import selection
        from fastapi import HTTPException
        baseline={model:(await self.db.execute(select(func.count()).select_from(model).where(model.company_id==self.company.id))).scalar_one() for model in [InventoryMovement,Sale]}
        archived=(await self.db.execute(select(Product).where(Product.company_id==self.company.id,Product.active.is_(False)))).scalars().one()
        deleted=(await self.db.execute(select(Product).where(Product.company_id==self.company.id,Product.deleted.is_(True)))).scalars().one()
        foreign_company=Company(name='Synthetic foreign catalogue',owner_email=f'{uuid4()}@example.test');self.db.add(foreign_company);await self.db.flush()
        foreign=Product(company_id=foreign_company.id,name='Synthetic foreign selected product',active=True);self.db.add(foreign);await self.db.commit()
        for selected in [archived.id,deleted.id,foreign.id,uuid4()]:
            for purpose in ['general','charge']:
                response=await self.get(purpose=purpose,selected_id=str(selected))
                self.assertEqual(response.status_code,200,response.text)
                self.assertEqual(response.json()['items'],[]);self.assertEqual(response.json()['total'],0)
                direct=await selection(self.db,self.company.id,self.branch.id,actor=self.owner,purpose=purpose,selected_id=selected)
                self.assertEqual(direct['items'],[])
        for purpose in ['management','recipe','components','GENERAL']:
            self.assertEqual((await self.get(purpose=purpose)).status_code,422)
            with self.assertRaises(HTTPException) as rejected:
                await selection(self.db,self.company.id,self.branch.id,actor=self.owner,purpose=purpose)
            self.assertEqual(rejected.exception.status_code,422)
        self.assertFalse(archived.active);self.assertTrue(deleted.deleted)
        for model in [InventoryMovement,Sale]:
            self.assertEqual((await self.db.execute(select(func.count()).select_from(model).where(model.company_id==self.company.id))).scalar_one(),baseline[model])

    async def test_sales_read_permission_does_not_grant_catalogue_edit_or_charge_configuration(self):
        from app.products.selection import selection
        from app.auth.dependencies import AuthActor
        from fastapi import HTTPException
        self.employee.permissions={'sales':True,'manage_products':False,'manage_inventory':False,'products_edit':False,'business_settings_manage':False}
        await self.db.commit()
        token=create_employee_access_token(employee_id=str(self.employee.id),company_id=str(self.company.id),role='cashier')
        headers={'Authorization':'Bearer '+token}
        result=await self.client.get(f'/api/products/{self.company.id}/selection',params={'branch_id':str(self.branch.id),'selected_id':str(self.product.id)},headers=headers)
        self.assertEqual(result.status_code,200,result.text);self.assertEqual(len(result.json()['items']),1);self.assertNotIn('cost_price',result.json()['items'][0])
        edit=await self.client.patch(f'/api/products/{self.company.id}/{self.product.id}',json={'name':'Forbidden catalogue rename'},headers=headers)
        self.assertEqual(edit.status_code,403,edit.text)
        actor=AuthActor(actor_type='employee',company_id=self.company.id,role='cashier',employee=self.employee,permissions=self.employee.permissions,pos_session=self.session)
        with self.assertRaises(HTTPException) as denied:
            await selection(self.db,self.company.id,self.branch.id,actor=actor,purpose='charge')
        self.assertEqual(denied.exception.status_code,403)
        charge=await self.client.get(f'/api/products/{self.company.id}/selection',params={'branch_id':str(self.branch.id),'purpose':'charge'},headers=headers)
        self.assertEqual(charge.status_code,403,charge.text)
