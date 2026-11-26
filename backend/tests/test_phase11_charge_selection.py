"""Read-only eligible charge search plus independent final profile validation."""
import unittest
from uuid import uuid4,UUID
from decimal import Decimal
from sqlalchemy import select,func,text
from fastapi import HTTPException
from app.models import Product,Company,Branch,CompanySubscription,InventoryMovement,Sale
from app.auth.security import create_employee_access_token
from app.auth.dependencies import resolve_auth_actor
from app.products.selection import selection
from app.business_operations.service import BusinessService
from app.business_operations.schema import ProfileInput
import test_phase11_product_selection as fixtures

class ChargeSelectionTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.ProductSelectionTests.cleanup
    asyncSetUp=fixtures.ProductSelectionTests.asyncSetUp
    async def get(self,**params):
        return await self.client.get(f'/api/products/{self.company.id}/selection',params={'branch_id':str(self.branch.id),'purpose':'charge',**params})
    async def seed(self):
        self.eligible=[]
        for n in range(31):
            row=Product(company_id=self.company.id,name=f'Charge choice {n:04}',sku=f'CHARGE-{n}',product_type='service' if n%2 else 'non_stock',track_inventory=False,selling_price=3,cost_price=99);self.db.add(row);self.eligible.append(row)
        literal=Product(company_id=self.company.id,name='Charge_%literal',product_type='service',track_inventory=False);self.db.add(literal)
        self.denied=[]
        for attributes in ({'product_type':'service','track_inventory':True},{'product_type':'standard','track_inventory':False},{'product_type':'service','track_inventory':False,'active':False},{'product_type':'service','track_inventory':False,'deleted':True}):
            row=Product(company_id=self.company.id,name='Charge choice excluded '+str(uuid4()),**attributes);self.db.add(row);self.denied.append(row)
        other=Company(name='Synthetic foreign charge tenant',owner_email=str(uuid4())+'@example.com');self.db.add(other);await self.db.flush()
        self.foreign=Product(company_id=other.id,name='Charge choice foreign',product_type='service',track_inventory=False);self.db.add(self.foreign);await self.db.commit()
        return literal
    async def test_count_pages_exact_lookup_literal_search_and_no_cost_or_effects(self):
        literal=await self.seed()
        first=await self.get();second=await self.get(page=2)
        self.assertEqual(first.status_code,200,first.text);self.assertEqual(first.json()['total'],32);self.assertEqual(len(first.json()['items']),25);self.assertEqual(len(second.json()['items']),7)
        ids={r['id'] for r in first.json()['items']};self.assertTrue(ids.isdisjoint(r['id'] for r in second.json()['items']))
        for row in first.json()['items']+second.json()['items']:
            self.assertFalse(row['track_inventory']);self.assertIn(row['product_type'],{'service','non_stock'});self.assertIsNone(row['branch_stock_qty']);self.assertNotIn('cost_price',row)
        self.assertEqual((await self.get(search='Charge_%literal')).json()['items'][0]['id'],str(literal.id))
        for row in self.denied+[self.foreign]:self.assertEqual((await self.get(selected_id=str(row.id))).json()['total'],0)
        target=self.eligible[-1];found=(await self.get(selected_id=str(target.id))).json();self.assertEqual(found['total'],1);self.assertEqual(found['items'][0]['name'],target.name)
        self.assertEqual((await self.get(purpose='recipe')).status_code,422)
        self.assertEqual((await self.db.execute(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.company_id==self.company.id))).scalar_one(),0)
    async def test_settings_only_role_branch_tenant_expiry_and_direct_current_identity(self):
        await self.seed();token=create_employee_access_token(employee_id=str(self.employee.id),company_id=str(self.company.id),role='cashier')
        path=f'/api/products/{self.company.id}/selection';params={'branch_id':str(self.branch.id),'purpose':'charge'};headers={'Authorization':'Bearer '+token}
        self.assertEqual((await self.client.get(path,params=params,headers=headers)).status_code,403)
        self.employee.permissions={'business_settings_manage':True,'sales':False,'manage_products':False,'manage_inventory':False};await self.db.commit()
        self.assertEqual((await self.client.get(path,params=params,headers=headers)).status_code,200)
        self.assertEqual((await self.client.get(path,params={**params,'purpose':'general'},headers=headers)).status_code,403)
        other=Branch(company_id=self.company.id,shop_id=self.shop.id,name='Other synthetic charge branch');self.db.add(other);await self.db.commit()
        self.assertEqual((await self.client.get(path,params={**params,'branch_id':str(other.id)},headers=headers)).status_code,403)
        self.assertEqual((await self.client.get(f'/api/products/{uuid4()}/selection',params=params)).status_code,403)
        with self.assertRaises(HTTPException) as denied:await selection(self.db,self.company.id,self.branch.id,purpose='charge')
        self.assertEqual(denied.exception.status_code,401)
        actor=await resolve_auth_actor(self.client.headers['Authorization'].split(' ',1)[1],self.db)
        for fields in ({'purpose':'recipe'},{'search':'x'*161},{'page':0},{'page_size':101},{'page':10**30}):
            with self.assertRaises(HTTPException) as invalid:await selection(self.db,self.company.id,self.branch.id,actor=actor,**fields)
            self.assertEqual(invalid.exception.status_code,422)
        sub=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one();sub.status='expired';await self.db.commit()
        self.assertEqual((await self.get()).status_code,200)
        await self.db.execute(text('UPDATE users SET session_version=session_version+1 WHERE id=:id'),{'id':self.user.id});await self.db.commit()
        with self.assertRaises(HTTPException) as revoked:await selection(self.db,self.company.id,self.branch.id,actor=actor,purpose='charge')
        self.assertEqual(revoked.exception.status_code,401)
    async def test_final_profile_service_refreshes_cached_eligibility_and_clear_has_no_stock_effect(self):
        await self.seed();product=self.eligible[0]
        before=(await self.db.execute(select(func.count()).select_from(Sale).where(Sale.company_id==self.company.id))).scalar_one()
        svc=BusinessService(self.db,self.owner)
        saved=await svc.save_profile(ProfileInput(profile='restaurant',tip_product_id=product.id,service_product_id=product.id));self.assertEqual(str(saved['tip_product_id']),str(product.id))
        await self.db.execute(text('UPDATE products SET track_inventory=true WHERE id=:id'),{'id':product.id});await self.db.commit();self.assertFalse(product.track_inventory)
        with self.assertRaises(HTTPException) as stale:await svc.save_profile(ProfileInput(profile='restaurant',tip_product_id=product.id))
        self.assertEqual(stale.exception.status_code,400)
        cleared=await svc.save_profile(ProfileInput(profile='restaurant'));self.assertIsNone(cleared['tip_product_id']);self.assertIsNone(cleared['service_product_id'])
        self.assertEqual((await self.db.execute(select(func.count()).select_from(Sale).where(Sale.company_id==self.company.id))).scalar_one(),before)
        self.assertEqual((await self.db.execute(select(func.count()).select_from(InventoryMovement).where(InventoryMovement.company_id==self.company.id))).scalar_one(),0)
