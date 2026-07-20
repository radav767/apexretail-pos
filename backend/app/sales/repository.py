from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.sale import Sale


class SalesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_product(self, product_id):
        result = await self.db.execute(
            select(Product)
            .where(
                Product.id == product_id,
                Product.active == True,
                Product.deleted == False,
            )
            .with_for_update()
        )

        return result.scalar_one_or_none()

    async def save_sale(
        self,
        sale,
        sale_items,
        products_to_update,
        inventory_movements,
    ):
        try:
            self.db.add(sale)
            self.db.add_all(sale_items)
            self.db.add_all(products_to_update)
            self.db.add_all(inventory_movements)

            await self.db.commit()
            await self.db.refresh(sale)

            return sale
        except Exception:
            await self.db.rollback()
            raise

    async def list_sales(self, company_id, limit: int = 100):
        result = await self.db.execute(
            select(Sale)
            .where(Sale.company_id == company_id)
            .order_by(Sale.created_at.desc())
            .limit(limit)
        )

        return result.scalars().all()
