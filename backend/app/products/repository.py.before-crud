from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.product import Product


class ProductRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_category(self, category: Category):
        self.db.add(category)
        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def list_categories(self, company_id: UUID):
        result = await self.db.execute(
            select(Category).where(
                Category.company_id == company_id,
                Category.deleted == False,
            ).order_by(Category.name)
        )
        return result.scalars().all()

    async def create_product(self, product: Product):
        self.db.add(product)
        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def list_products(self, company_id: UUID):
        result = await self.db.execute(
            select(Product).where(
                Product.company_id == company_id,
                Product.deleted == False,
            ).order_by(Product.name)
        )
        return result.scalars().all()
