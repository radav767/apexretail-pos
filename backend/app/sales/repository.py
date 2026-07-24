from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.inventory.stock_repository import BranchStockRepository
from app.models.sale import Sale


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
