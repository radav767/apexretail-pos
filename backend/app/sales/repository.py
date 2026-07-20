from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem


class SalesRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_product(self, product_id):
        result = await self.db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.deleted == False,
                Product.active == True,
            )
        )
        return result.scalar_one_or_none()

    async def save_sale(self, sale: Sale, items: list[SaleItem], products_to_update: list[Product]):
        self.db.add(sale)

        for item in items:
            self.db.add(item)

        for product in products_to_update:
            self.db.add(product)

        await self.db.commit()
        await self.db.refresh(sale)
        return sale

    async def list_sales(self, company_id, limit: int = 100):
        result = await self.db.execute(
            select(Sale)
            .where(Sale.company_id == company_id)
            .order_by(Sale.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
