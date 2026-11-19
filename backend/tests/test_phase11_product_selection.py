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
