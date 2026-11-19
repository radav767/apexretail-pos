from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.shop import Shop


class BranchStockRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_branch(
        self,
        company_id: UUID,
        branch_id: UUID | None = None,
    ) -> Branch:
        query = (
            select(Branch)
            .join(Shop, Shop.id == Branch.shop_id)
            .where(
                Branch.company_id == company_id,
                Shop.company_id == company_id,
                Branch.active == True,
                Branch.deleted == False,
                Shop.active == True,
                Shop.deleted == False,
            )
        )

        if branch_id is not None:
            query = query.where(Branch.id == branch_id)

        result = await self.db.execute(
            query.order_by(Branch.created_at.asc()).limit(1)
        )

        branch = result.scalar_one_or_none()

        if not branch:
            if branch_id is not None:
                raise HTTPException(
                    404,
                    "Branch not found or inactive",
                )

            raise HTTPException(
                400,
                "No active branch exists for this company",
            )

        return branch

    async def get_product_for_update(
        self,
        company_id: UUID,
        product_id: UUID,
    ) -> Product:
        result = await self.db.execute(
            select(Product)
            .where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.active == True,
                Product.deleted == False,
            )
            .with_for_update().execution_options(populate_existing=True)
        )

        product = result.scalar_one_or_none()

        if not product:
            raise HTTPException(404, "Product not found")

        return product

    async def get_balance_for_update(
        self,
        company_id: UUID,
        branch: Branch,
        product: Product,
    ) -> InventoryBalance:
        result = await self.db.execute(
            select(InventoryBalance)
            .where(
                InventoryBalance.company_id == company_id,
                InventoryBalance.branch_id == branch.id,
                InventoryBalance.product_id == product.id,
                InventoryBalance.deleted == False,
            )
            .with_for_update().execution_options(populate_existing=True)
        )

        balance = result.scalar_one_or_none()

        if balance:
            return balance

        existing_result = await self.db.execute(
            select(func.count(InventoryBalance.id)).where(
                InventoryBalance.company_id == company_id,
                InventoryBalance.product_id == product.id,
                InventoryBalance.active == True,
                InventoryBalance.deleted == False,
            )
        )

        existing_count = int(existing_result.scalar_one() or 0)

        initial_quantity = (
            Decimal(product.stock_qty or 0)
            if existing_count == 0
            else Decimal("0")
        )

        balance = InventoryBalance(
            company_id=company_id,
            shop_id=branch.shop_id,
            branch_id=branch.id,
            product_id=product.id,
            quantity=initial_quantity,
            reorder_level=Decimal(product.reorder_level or 0),
            active=True,
            deleted=False,
        )

        self.db.add(balance)
        await self.db.flush()

        return balance

    async def sync_product_total(
        self,
        product: Product,
    ) -> Decimal:
        await self.db.flush()

        result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(InventoryBalance.quantity),
                    0,
                )
            ).where(
                InventoryBalance.company_id == product.company_id,
                InventoryBalance.product_id == product.id,
                InventoryBalance.active == True,
                InventoryBalance.deleted == False,
            )
        )

        total = Decimal(result.scalar_one() or 0)
        product.stock_qty = total

        self.db.add(product)
        await self.db.flush()

        return total
