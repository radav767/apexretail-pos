from uuid import UUID

from fastapi import HTTPException

from app.models.category import Category
from app.models.product import Product
from app.products.repository import ProductRepository
from app.products.schema import (
    CategoryCreate,
    CategoryUpdate,
    ProductCreate,
    ProductUpdate,
)


class ProductService:
    def __init__(self, repo: ProductRepository):
        self.repo = repo

    async def create_category(self, data: CategoryCreate):
        name = data.name.strip()

        duplicate = await self.repo.find_category_by_name(
            data.company_id,
            name,
        )

        if duplicate:
            raise HTTPException(409, "Category already exists")

        category = Category(
            company_id=data.company_id,
            name=name,
            active=True,
            deleted=False,
        )

        return await self.repo.create_category(category)

    async def list_categories(self, company_id: UUID):
        return await self.repo.list_categories(company_id)

    async def update_category(
        self,
        company_id: UUID,
        category_id: UUID,
        data: CategoryUpdate,
    ):
        category = await self.repo.get_category(company_id, category_id)

        if not category:
            raise HTTPException(404, "Category not found")

        changes = data.model_dump(exclude_unset=True)

        if "name" in changes:
            changes["name"] = changes["name"].strip()

            duplicate = await self.repo.find_category_by_name(
                company_id,
                changes["name"],
                exclude_id=category_id,
            )

            if duplicate:
                raise HTTPException(409, "Category already exists")

        return await self.repo.update_category(category, changes)

    async def delete_category(
        self,
        company_id: UUID,
        category_id: UUID,
    ):
        category = await self.repo.get_category(company_id, category_id)

        if not category:
            raise HTTPException(404, "Category not found")

        await self.repo.delete_category(category)

        return {
            "ok": True,
            "message": "Category deleted",
        }

    async def create_product(self, data: ProductCreate):
        values = data.model_dump()

        values["name"] = values["name"].strip()
        values["unit"] = values["unit"].strip().lower() or "each"
        values["sku"] = self._clean_optional(values.get("sku"))
        values["barcode"] = self._clean_optional(values.get("barcode"))

        await self._validate_category(
            data.company_id,
            values.get("category_id"),
        )

        conflict = await self.repo.find_product_conflict(
            data.company_id,
            values.get("sku"),
            values.get("barcode"),
        )

        if conflict:
            raise HTTPException(
                409,
                "Another product already uses this SKU or barcode",
            )

        product = Product(
            **values,
            active=True,
            deleted=False,
        )

        return await self.repo.create_product(product)

    async def list_products(self, company_id: UUID):
        return await self.repo.list_products(company_id)

    async def update_product(
        self,
        company_id: UUID,
        product_id: UUID,
        data: ProductUpdate,
    ):
        product = await self.repo.get_product(company_id, product_id)

        if not product:
            raise HTTPException(404, "Product not found")

        changes = data.model_dump(exclude_unset=True)

        if "name" in changes:
            changes["name"] = changes["name"].strip()

        if "unit" in changes and changes["unit"] is not None:
            changes["unit"] = changes["unit"].strip().lower() or "each"

        if "sku" in changes:
            changes["sku"] = self._clean_optional(changes["sku"])

        if "barcode" in changes:
            changes["barcode"] = self._clean_optional(
                changes["barcode"]
            )

        if "category_id" in changes:
            await self._validate_category(
                company_id,
                changes["category_id"],
            )

        resulting_sku = changes.get("sku", product.sku)
        resulting_barcode = changes.get("barcode", product.barcode)

        conflict = await self.repo.find_product_conflict(
            company_id,
            resulting_sku,
            resulting_barcode,
            exclude_id=product_id,
        )

        if conflict:
            raise HTTPException(
                409,
                "Another product already uses this SKU or barcode",
            )

        return await self.repo.update_product(product, changes)

    async def delete_product(
        self,
        company_id: UUID,
        product_id: UUID,
    ):
        product = await self.repo.get_product(company_id, product_id)

        if not product:
            raise HTTPException(404, "Product not found")

        await self.repo.delete_product(product)

        return {
            "ok": True,
            "message": "Product deleted",
        }

    async def _validate_category(
        self,
        company_id: UUID,
        category_id: UUID | None,
    ):
        if category_id is None:
            return

        category = await self.repo.get_category(
            company_id,
            category_id,
        )

        if not category or not category.active:
            raise HTTPException(
                400,
                "Invalid or inactive category",
            )

    @staticmethod
    def _clean_optional(value: str | None):
        if value is None:
            return None

        cleaned = value.strip()
        return cleaned or None
