from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.shop import Shop


class BranchInventoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_branches(self, company_id: UUID):
        result = await self.db.execute(
            select(
                Branch.id,
                Branch.shop_id,
                Shop.name.label("shop_name"),
                Branch.name,
            )
            .join(Shop, Shop.id == Branch.shop_id)
            .where(
                Branch.company_id == company_id,
                Branch.active == True,
                Branch.deleted == False,
                Shop.active == True,
                Shop.deleted == False,
            )
            .order_by(
                Shop.name.asc(),
                Branch.name.asc(),
            )
        )

        return result.mappings().all()

    async def list_balances(
        self,
        company_id: UUID,
        branch_id: UUID | None,
    ):
        query = (
            select(
                InventoryBalance.branch_id,
                Branch.name.label("branch_name"),
                InventoryBalance.shop_id,
                Shop.name.label("shop_name"),
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.sku,
                Product.unit,
                InventoryBalance.quantity,
                InventoryBalance.reorder_level,
                Product.cost_price,
            )
            .join(
                Branch,
                Branch.id == InventoryBalance.branch_id,
            )
            .join(
                Shop,
                Shop.id == InventoryBalance.shop_id,
            )
            .join(
                Product,
                Product.id == InventoryBalance.product_id,
            )
            .where(
                InventoryBalance.company_id == company_id,
                InventoryBalance.active == True,
                InventoryBalance.deleted == False,
                Branch.active == True,
                Branch.deleted == False,
                Shop.active == True,
                Shop.deleted == False,
                Product.active == True,
                Product.deleted == False,
            )
        )

        if branch_id is not None:
            query = query.where(
                InventoryBalance.branch_id == branch_id,
            )

        result = await self.db.execute(
            query.order_by(
                Shop.name.asc(),
                Branch.name.asc(),
                Product.name.asc(),
            )
        )

        return result.mappings().all()
