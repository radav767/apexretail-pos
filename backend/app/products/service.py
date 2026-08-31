from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.category import Category
from app.models.product import Product
from app.models.audit_event import AuditEvent
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
        branch_id = values.pop("branch_id", None)
        opening_quantity = values.pop("stock_qty")
        create_request_key = self._clean_optional(
            values.pop("create_request_key", None)
        )

        values["name"] = values["name"].strip()
        values["unit"] = values["unit"].strip().lower() or "each"
        values["sku"] = self._clean_optional(values.get("sku"))
        values["barcode"] = self._clean_optional(values.get("barcode"))

        if create_request_key:
            existing = await self.repo.get_by_create_request_key(
                data.company_id,
                create_request_key,
            )

            if existing:
                return existing

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

        if branch_id is not None or opening_quantity > 0:
            branch = await self.repo.resolve_branch(
                data.company_id,
                branch_id,
            )
            branch_id = branch.id

        product = Product(
            **values,
            create_request_key=create_request_key,
            stock_qty=0,
            active=True,
            deleted=False,
        )

        try:
            return await self.repo.create_product(
                product,
                opening_quantity=opening_quantity,
                branch_id=branch_id,
            )
        except IntegrityError:
            if create_request_key:
                existing = await self.repo.get_by_create_request_key(
                    data.company_id,
                    create_request_key,
                )

                if existing:
                    return existing

            raise

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

        if "stock_qty" in changes:
            changes.pop("stock_qty")

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
        actor=None,
    ):
        product = await self.repo.get_product(company_id, product_id)

        if not product:
            raise HTTPException(404, "Product not found")

        before = {"active": bool(product.active), "deleted": bool(product.deleted), "archived_at": str(product.archived_at) if product.archived_at else None}
        self.repo.db.add(AuditEvent(company_id=company_id, actor_employee_id=actor.employee.id if actor and actor.actor_type == "employee" else None, actor_user_id=actor.user.id if actor and actor.actor_type == "user" else None, action="product_archive", reason="Product archived", details={"record_id": str(product.id), "before": before, "after": {"active": False, "deleted": False}}))
        await self.repo.delete_product(product)

        return {
            "ok": True,
            "message": "Product deleted",
        }

    async def archive_product(self, company_id: UUID, product_id: UUID, actor=None):
        product = await self.repo.get_product(company_id, product_id)
        if not product:
            raise HTTPException(404, "Product not found")
        return await self.delete_product(company_id, product_id, actor=actor)

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
