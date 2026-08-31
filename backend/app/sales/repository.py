from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.inventory.stock_repository import BranchStockRepository
from app.models.device import Device
from app.models.sale import Sale
from app.models.employee import Employee
from app.models.sale_item import SaleItem
from app.models.shop import Shop
from app.models.inventory_movement import InventoryMovement


class SalesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
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
        return await self.stock.get_product_for_update(
            company_id,
            product_id,
        )

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

    async def sync_product_total(self, product):
        return await self.stock.sync_product_total(product)

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
        )

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

    async def save_sale(
        self,
        sale,
        sale_items,
        products,
        balances,
        inventory_movements,
    ):
        try:
            self.db.add(sale)
            self.db.add_all(sale_items)
            self.db.add_all(products)
            self.db.add_all(balances)
            self.db.add_all(inventory_movements)

            await self.db.commit()
            await self.db.refresh(sale)

            return sale
        except Exception:
            await self.db.rollback()
            raise

    async def list_sales(
        self,
        company_id,
        limit: int = 100,
    ):
        result = await self.db.execute(
            select(Sale)
            .where(Sale.company_id == company_id)
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
