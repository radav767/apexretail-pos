from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.inventory.stock_repository import BranchStockRepository
from app.models.device import Device
from app.models.sale import Sale
from app.models.employee import Employee
from app.models.sale_item import SaleItem
from app.models.sale_item_component import SaleItemComponent
from app.models.product_component import ProductComponent
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.product_price_level import ProductPriceLevel
from app.models.variant_inventory_balance import VariantInventoryBalance
from app.models.shop import Shop
from app.models.inventory_movement import InventoryMovement
from app.models.category import Category
from app.models.customer import Customer
from app.models.credit_receivable import CreditReceivable
from app.models.company_settings import CompanySetting


class SalesRepository:
    async def credit_receivable_for_update(self, company_id, sale_id):
        return (await self.db.execute(select(CreditReceivable).where(CreditReceivable.company_id == company_id,
            CreditReceivable.sale_id == sale_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()

    async def begin_refund_command(self, data, actor):
        from .refund_commands import begin
        return await begin(self.db, data, actor)

    def record_refund_command(self, data, proof, refund, device):
        from .refund_commands import record
        record(self.db, data, proof, refund, device)

    async def begin_command(self, data, actor):
        from app.sales.commands import begin
        return await begin(self.db, data, actor)

    def record_command(self, data, proof, sale, device):
        from app.sales.commands import record
        record(self.db, data, proof, sale, device)

    def __init__(self, db: AsyncSession, *, commit_on_save: bool = True):
        self.db = db
        self.commit_on_save = commit_on_save
        self.stock = BranchStockRepository(db)

    async def resolve_branch(
        self,
        company_id,
        branch_id=None,
    ):
        return await self.stock.resolve_branch(
            company_id,
            branch_id,
        )

    async def get_product(
        self,
        company_id,
        product_id,
    ):
        product = await self.stock.get_product_for_update(
            company_id,
            product_id,
        )
        return product

    async def validate_new_sale_product(self, company_id, product_id):
        from app.models import TipSettings, BusinessProfile
        config = await self.db.get(TipSettings, company_id)
        profile = await self.db.get(BusinessProfile, company_id) if config else None
        if profile and profile.tip_product_id == product_id:
            from fastapi import HTTPException
            raise HTTPException(409, "Record tips through the separate tip workflow. Retain existing queued sales for review; do not silently reclassify them")

    async def get_category_name(self, company_id, category_id):
        result = await self.db.execute(
            select(Category.name).where(
                Category.company_id == company_id,
                Category.id == category_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_balance(
        self,
        company_id,
        branch,
        product,
    ):
        return await self.stock.get_balance_for_update(
            company_id,
            branch,
            product,
        )
    async def get_variant(self,company_id,product_id,variant_id):
        return (await self.db.execute(select(ProductVariant).where(ProductVariant.company_id==company_id,ProductVariant.product_id==product_id,ProductVariant.id==variant_id,ProductVariant.active==True,ProductVariant.deleted==False).with_for_update())).scalar_one_or_none()

    async def has_active_variants(self, company_id, product_id):
        return (await self.db.execute(select(ProductVariant.id).where(ProductVariant.company_id == company_id,
            ProductVariant.product_id == product_id, ProductVariant.active == True,
            ProductVariant.deleted == False).limit(1))).first() is not None
    async def get_variant_balance(self,company_id,branch,product_id,variant_id):
        row=(await self.db.execute(select(VariantInventoryBalance).where(VariantInventoryBalance.company_id==company_id,VariantInventoryBalance.branch_id==branch.id,VariantInventoryBalance.variant_id==variant_id,VariantInventoryBalance.deleted==False).with_for_update())).scalar_one_or_none()
        if row is None:
            row=VariantInventoryBalance(company_id=company_id,shop_id=branch.shop_id,branch_id=branch.id,product_id=product_id,variant_id=variant_id,quantity=0,reorder_level=0); self.db.add(row); await self.db.flush()
        return row
    async def get_price_level(self,company_id,product_id,name,quantity):
        return (await self.db.execute(select(ProductPriceLevel).where(ProductPriceLevel.company_id==company_id,ProductPriceLevel.product_id==product_id,func.lower(ProductPriceLevel.name)==name.lower(),ProductPriceLevel.minimum_quantity<=quantity,ProductPriceLevel.active==True,ProductPriceLevel.deleted==False).order_by(ProductPriceLevel.minimum_quantity.desc()).limit(1))).scalar_one_or_none()

    async def sync_product_total(self, product):
        return await self.stock.sync_product_total(product)

    async def get_product_components(self, company_id, composite_product_id):
        result = await self.db.execute(
            select(ProductComponent, Product)
            .join(Product, Product.id == ProductComponent.component_product_id)
            .where(
                ProductComponent.company_id == company_id,
                ProductComponent.composite_product_id == composite_product_id,
                ProductComponent.active == True,
                ProductComponent.deleted == False,
                Product.company_id == company_id,
                Product.active == True,
                Product.deleted == False,
            )
            .order_by(Product.id.asc())
        )
        return result.all()

    async def get_sale_item_components(self, company_id, sale_item_id):
        result = await self.db.execute(
            select(SaleItemComponent).where(
                SaleItemComponent.company_id == company_id,
                SaleItemComponent.sale_item_id == sale_item_id,
            )
        )
        return result.scalars().all()

    async def get_by_client_sale_id(
        self,
        company_id,
        client_sale_id,
    ):
        if client_sale_id is None:
            return None

        result = await self.db.execute(
            select(Sale).where(
                Sale.company_id == company_id,
                Sale.client_sale_id == client_sale_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_device(
        self,
        company_id,
        *,
        device_id=None,
        device_key=None,
    ):
        query = select(Device).where(
            Device.company_id == company_id,
            Device.deleted == False,
        ).with_for_update()

        if device_id is not None:
            query = query.where(Device.id == device_id)
        elif device_key is not None:
            query = query.where(Device.device_key == device_key)
        else:
            return None

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_shop(
        self,
        company_id,
        shop_id,
    ):
        result = await self.db.execute(
            select(Shop).where(
                Shop.company_id == company_id,
                Shop.id == shop_id,
                Shop.deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def get_customer_for_update(self, company_id, customer_id):
        result = await self.db.execute(
            select(Customer).where(
                Customer.company_id == company_id,
                Customer.id == customer_id,
                Customer.active.is_(True),
                Customer.deleted.is_(False),
            ).with_for_update()
        )
        return result.scalar_one_or_none()

    async def customer_outstanding(self, company_id, customer_id):
        result = await self.db.execute(
            select(func.coalesce(func.sum(CreditReceivable.outstanding_balance), 0)).where(
                CreditReceivable.company_id == company_id,
                CreditReceivable.customer_id == customer_id,
            )
        )
        return result.scalar_one()

    async def get_currency_code(self, company_id):
        result = await self.db.execute(
            select(CompanySetting.currency_code).where(
                CompanySetting.company_id == company_id,
                CompanySetting.deleted.is_(False),
            )
        )
        return result.scalar_one_or_none() or "USD"

    async def save_sale(
        self,
        sale,
        sale_items,
        products,
        balances,
        inventory_movements,
        sale_item_components=None,
    ):
        try:
            self.db.add(sale)
            self.db.add_all(sale_items)
            self.db.add_all(products)
            self.db.add_all(balances)
            self.db.add_all(inventory_movements)
            self.db.add_all(sale_item_components or [])

            from app.business_operations.batches import allocate_batch_movements
            await allocate_batch_movements(self.db, inventory_movements)
            if self.commit_on_save:
                await self.db.commit()
            else:
                await self.db.flush()
            await self.db.refresh(sale)

            return sale
        except Exception:
            await self.db.rollback()
            raise

    async def save_credit_sale(
        self,
        sale,
        sale_items,
        products,
        balances,
        inventory_movements,
        receivable,
        audit_event,
        sale_item_components=None,
    ):
        try:
            self.db.add(sale)
            self.db.add_all(sale_items)
            self.db.add_all(products)
            self.db.add_all(balances)
            self.db.add_all(inventory_movements)
            self.db.add_all(sale_item_components or [])
            # Establish the sale FK target before adding its receivable while
            # keeping every write inside this same database transaction.
            await self.db.flush()
            self.db.add(receivable)
            self.db.add(audit_event)
            from app.business_operations.batches import allocate_batch_movements
            await allocate_batch_movements(self.db, inventory_movements)
            if self.commit_on_save:
                await self.db.commit()
            else:
                await self.db.flush()
            await self.db.refresh(sale)
            return sale
        except Exception:
            await self.db.rollback()
            raise

    async def list_sales(
        self,
        company_id,
        limit: int = 100,
        branch_id=None,
    ):
        statement = select(Sale).where(Sale.company_id == company_id)
        if branch_id is not None:
            statement = statement.where(Sale.branch_id == branch_id)
        result = await self.db.execute(
            statement
            .order_by(Sale.created_at.desc())
            .limit(limit)
        )

        return result.scalars().all()

    async def get_sale_receipt(
        self,
        company_id,
        sale_id,
    ):
        result = await self.db.execute(
            select(Sale)
            .where(
                Sale.company_id == company_id,
                Sale.id == sale_id,
            )
        )
        sale = result.scalar_one_or_none()

        if sale is None:
            return None

        items_result = await self.db.execute(
            select(SaleItem)
            .where(SaleItem.sale_id == sale.id)
            .order_by(SaleItem.id.asc())
        )

        return sale, items_result.scalars().all()

    async def get_sale(
        self,
        company_id,
        sale_id,
    ):
        result = await self.db.execute(
            select(Sale).where(
                Sale.company_id == company_id,
                Sale.id == sale_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_sale_for_update(self, company_id, sale_id):
        result = await self.db.execute(select(Sale).where(Sale.company_id == company_id, Sale.id == sale_id).with_for_update())
        return result.scalar_one_or_none()

    async def get_sale_items(
        self,
        sale_id,
    ):
        result = await self.db.execute(
            select(SaleItem).where(
                SaleItem.sale_id == sale_id,
            )
        )
        return result.scalars().all()

    async def get_sale_items_for_update(self, sale_id):
        result = await self.db.execute(select(SaleItem).where(SaleItem.sale_id == sale_id).with_for_update())
        return result.scalars().all()

    async def list_refund_items_for_original_item(
        self,
        original_sale_item_id,
    ):
        result = await self.db.execute(
            select(SaleItem).where(
                SaleItem.original_sale_item_id == original_sale_item_id,
            )
        )
        return result.scalars().all()

    async def get_employee(
        self,
        employee_id,
        company_id=None,
        branch_id=None,
    ):
        query = select(Employee).where(
            Employee.id == employee_id,
            Employee.active.is_(True),
            Employee.deleted.is_(False),
        )

        if company_id is not None:
            query = query.where(
                Employee.company_id == company_id
            )

        if branch_id is not None:
            query = query.where(
                Employee.branch_id == branch_id
            )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()
