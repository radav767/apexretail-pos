from uuid import UUID

from sqlalchemy import or_, select, update
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
            select(Category)
            .where(
                Category.company_id == company_id,
                Category.deleted == False,
            )
            .order_by(Category.name.asc())
        )
        return result.scalars().all()

    async def get_category(self, company_id: UUID, category_id: UUID):
        result = await self.db.execute(
            select(Category).where(
                Category.id == category_id,
                Category.company_id == company_id,
                Category.deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def find_category_by_name(
        self,
        company_id: UUID,
        name: str,
        exclude_id: UUID | None = None,
    ):
        query = select(Category).where(
            Category.company_id == company_id,
            Category.deleted == False,
            Category.name.ilike(name),
        )

        if exclude_id:
            query = query.where(Category.id != exclude_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_category(self, category: Category, changes: dict):
        for field, value in changes.items():
            setattr(category, field, value)

        await self.db.commit()
        await self.db.refresh(category)
        return category

    async def delete_category(self, category: Category):
        category.active = False
        category.deleted = True

        # Products remain active but become uncategorized.
        await self.db.execute(
            update(Product)
            .where(
                Product.category_id == category.id,
                Product.company_id == category.company_id,
            )
            .values(category_id=None)
        )

        await self.db.commit()
        return category

    async def create_product(self, product: Product):
        self.db.add(product)
        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def list_products(self, company_id: UUID):
        result = await self.db.execute(
            select(Product)
            .where(
                Product.company_id == company_id,
                Product.deleted == False,
            )
            .order_by(Product.name.asc())
        )
        return result.scalars().all()

    async def get_product(self, company_id: UUID, product_id: UUID):
        result = await self.db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def find_product_conflict(
        self,
        company_id: UUID,
        sku: str | None,
        barcode: str | None,
        exclude_id: UUID | None = None,
    ):
        conditions = []

        if sku:
            conditions.append(Product.sku.ilike(sku))

        if barcode:
            conditions.append(Product.barcode.ilike(barcode))

        if not conditions:
            return None

        query = select(Product).where(
            Product.company_id == company_id,
            Product.deleted == False,
            or_(*conditions),
        )

        if exclude_id:
            query = query.where(Product.id != exclude_id)

        result = await self.db.execute(query)
        return result.scalars().first()

    async def update_product(self, product: Product, changes: dict):
        for field, value in changes.items():
            setattr(product, field, value)

        await self.db.commit()
        await self.db.refresh(product)
        return product

    async def delete_product(self, product: Product):
        product.active = False
        product.deleted = True

        await self.db.commit()
        return product
