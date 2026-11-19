"""Current catalog license/module policy with real SQL and API boundaries."""
from io import BytesIO
from uuid import uuid4
from decimal import Decimal
import unittest
from unittest.mock import AsyncMock
import httpx
from fastapi import HTTPException, UploadFile
from sqlalchemy import select, func
from app.models import CompanySubscription, Product, Category, ProductVariant, ProductPriceLevel, ProductComponent, ProductMedia, InventoryMovement, AuditEvent
from app.auth.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.products.repository import ProductRepository
from app.products.service import ProductService
from app.products.media import store
from app.products.schema import (CategoryCreate,CategoryUpdate,ProductCreate,ProductUpdate,ProductComponentWrite,
    ProductVariantCreate,ProductVariantUpdate,ProductPriceLevelCreate,ProductPriceLevelUpdate,ProductImportRequest,ProductImportRow)
import test_phase7d_operations as fixtures


class CatalogPolicyTests(unittest.IsolatedAsyncioTestCase):
    cleanup=fixtures.Phase7DOperationsTests.cleanup
    async def asyncSetUp(self):
        await fixtures.Phase7DOperationsTests.asyncSetUp(self)
        self.repo=ProductRepository(self.db);self.catalog=ProductService(self.repo)
        self.license=(await self.db.execute(select(CompanySubscription).where(CompanySubscription.company_id==self.company.id))).scalar_one()
        self.product.barcode='SYNTHETIC-'+str(uuid4());await self.db.commit()
        self.variant=await self.catalog.create_variant(self.company.id,self.product.id,ProductVariantCreate(name='Synthetic variant'))
        self.level=await self.catalog.create_price_level(self.company.id,self.product.id,ProductPriceLevelCreate(name='Synthetic tier',price=8))
        self.composite=await self.catalog.create_product(ProductCreate(company_id=self.company.id,name='Synthetic bundle',product_type='composite'))
        async def override():yield self.db
        app.dependency_overrides[get_db]=override;self.addCleanup(app.dependency_overrides.clear)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://synthetic.test',headers={'Authorization':'Bearer '+create_access_token(str(self.user.id),self.user.email)})
        self.addAsyncCleanup(self.client.aclose)
    async def counts(self):
        return tuple([(await self.db.execute(select(func.count(model.id)).where(model.company_id==self.company.id))).scalar_one()
                     for model in (Product,Category,ProductVariant,ProductPriceLevel,ProductComponent,ProductMedia,InventoryMovement,AuditEvent)])
    async def deny(self,operation,status=402):
        with self.assertRaises(HTTPException) as error:await operation
        self.assertEqual(error.exception.status_code,status)
    async def test_all_direct_catalog_mutations_denied_before_any_effect_after_expiry(self):
        self.license.status='expired';await self.db.commit();before=await self.counts()
        company=self.company.id;product=self.product.id;variant=self.variant['id'];level=self.level.id
        operations=[
            self.catalog.create_category(CategoryCreate(company_id=company,name='Denied')),
            self.catalog.update_category(company,self.category.id,CategoryUpdate(name='Denied')),
            self.catalog.delete_category(company,self.category.id),
            self.catalog.create_product(ProductCreate(company_id=company,name='Denied',stock_qty=4,branch_id=self.branch.id)),
            self.catalog.update_product(company,product,ProductUpdate(selling_price=99)),
            self.catalog.delete_product(company,product),self.catalog.archive_product(company,product),
            self.catalog.replace_components(company,self.composite.id,[ProductComponentWrite(component_product_id=product,quantity=2)]),
            self.catalog.create_variant(company,product,ProductVariantCreate(name='Denied',branch_id=self.branch.id,stock_qty=4)),
            self.catalog.update_variant(company,variant,ProductVariantUpdate(name='Denied',branch_id=self.branch.id,stock_qty=44)),
            self.catalog.delete_variant(company,variant),
            self.catalog.create_price_level(company,product,ProductPriceLevelCreate(name='Denied',price=1)),
            self.catalog.update_price_level(company,level,ProductPriceLevelUpdate(price=1)),self.catalog.delete_price_level(company,level),
            self.catalog.import_products(ProductImportRequest(company_id=company,branch_id=self.branch.id,rows=[ProductImportRow(name='Denied',category_name='Denied',stock_qty=7)])),
        ]
        for operation in operations:await self.deny(operation)
        upload=UploadFile(BytesIO(b'synthetic image'),filename='synthetic.png');upload.read=AsyncMock(side_effect=AssertionError('Must not read/write image on denial'))
        await self.deny(store(self.repo,company,product,upload));upload.read.assert_not_awaited()
        self.assertEqual(await self.counts(),before);self.assertEqual(self.balance.quantity,100);self.assertEqual(self.product.selling_price,Decimal('12'))
    async def test_optional_module_preflight_prevents_partial_import_and_preserves_historical_reads(self):
        self.license.commercial_terms={'features':{'variants':False,'composites':False}};await self.db.commit()
        company=self.company.id;product=self.product.id;before=await self.counts()
        for module_row in (ProductImportRow(name='Optional variant',variant_name='Size',variant_stock_qty=5),ProductImportRow(name='Optional bundle',product_type='bundle')):
            await self.deny(self.catalog.import_products(ProductImportRequest(company_id=company,branch_id=self.branch.id,rows=[ProductImportRow(name='Must not import',category_name='Must not create',stock_qty=9),module_row])),403)
        await self.deny(self.catalog.create_product(ProductCreate(company_id=company,name='Optional',product_type='bundle')),403)
        await self.deny(self.catalog.update_product(company,self.composite.id,ProductUpdate(name='Optional edit')),403)
        await self.deny(self.catalog.replace_components(company,self.composite.id,[ProductComponentWrite(component_product_id=product,quantity=1)]),403)
        await self.deny(self.catalog.create_variant(company,product,ProductVariantCreate(name='Optional')),403)
        await self.deny(self.catalog.update_variant(company,self.variant['id'],ProductVariantUpdate(name='Optional')),403)
        await self.deny(self.catalog.delete_variant(company,self.variant['id']),403)
        self.assertEqual(await self.counts(),before)
        # Ordinary tiers keep the existing contract without an invented wholesale gate.
        updated=await self.catalog.update_price_level(company,self.level.id,ProductPriceLevelUpdate(price=7))
        self.assertEqual(updated.price,7)
        self.license.status='expired';await self.db.commit()
        for path in (f'/api/products/{company}',f'/api/products/categories/{company}',f'/api/products/components/{company}/{self.composite.id}',
                     f'/api/products/variants/{company}',f'/api/products/price-levels/{company}',
                     f'/api/products/{company}/barcode-lookup?branch_id={self.branch.id}&barcode={self.product.barcode}'):
            response=await self.client.get(path);self.assertEqual(response.status_code,200,(path,response.text))
        foreign=await self.client.get(f'/api/products/{uuid4()}');self.assertEqual(foreign.status_code,403)
    async def test_api_update_archive_and_delete_no_longer_bypass_license(self):
        self.license.status='expired';await self.db.commit();before=await self.counts();base=f'/api/products/{self.company.id}/{self.product.id}'
        for method,path,body in [('PATCH',base,{'selling_price':'99'}),('POST',base+'/archive',None),('DELETE',base,None)]:
            response=await self.client.request(method,path,json=body);self.assertEqual(response.status_code,402,response.text)
        self.assertEqual(await self.counts(),before);self.assertTrue(self.product.active)
    async def test_legacy_creation_retry_preserves_opening_stock_but_is_not_an_expiry_exception(self):
        command=ProductCreate(company_id=self.company.id,branch_id=self.branch.id,name='Synthetic opening',stock_qty=3,create_request_key='catalog-'+str(uuid4()))
        first=await self.catalog.create_product(command);before=await self.counts()
        second=await self.catalog.create_product(command);self.assertEqual(first.id,second.id);self.assertEqual(await self.counts(),before)
        movements=(await self.db.execute(select(InventoryMovement).where(InventoryMovement.product_id==first.id))).scalars().all()
        self.assertEqual(len(movements),1);self.assertEqual(movements[0].quantity,3)
        self.license.status='expired';await self.db.commit();await self.deny(self.catalog.create_product(command))
        self.assertEqual(await self.counts(),before)
