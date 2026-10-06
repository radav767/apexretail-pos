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
            self._raise_product_conflict(
                conflict,
                values.get("sku"),
                values.get("barcode"),
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
        except IntegrityError as error:
            if create_request_key:
                existing = await self.repo.get_by_create_request_key(
                    data.company_id,
                    create_request_key,
                )

                if existing:
                    return existing
            self._raise_barcode_integrity_error(error)
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
            self._raise_product_conflict(
                conflict,
                resulting_sku,
                resulting_barcode,
            )

        try:
            return await self.repo.update_product(product, changes)
        except IntegrityError as error:
            self._raise_barcode_integrity_error(error)
            raise

    async def lookup_barcode(
        self,
        company_id: UUID,
        branch_id: UUID,
        barcode: str,
    ):
        normalized = self._clean_optional(barcode)
        if not normalized:
            raise HTTPException(400, "Barcode is required")

        branch = await self.repo.resolve_branch(company_id, branch_id)
        product = await self.repo.find_active_by_barcode(
            company_id,
            normalized,
        )
        if product is None:
            raise HTTPException(404, "Product Not Found")

        branch_stock_qty = await self.repo.get_branch_stock_quantity(
            company_id,
            branch.id,
            product.id,
        )
        return {
            "id": product.id,
            "company_id": product.company_id,
            "category_id": product.category_id,
            "name": product.name,
            "sku": product.sku,
            "barcode": product.barcode,
            "unit": product.unit,
            "cost_price": product.cost_price,
            "selling_price": product.selling_price,
            "stock_qty": product.stock_qty,
            "reorder_level": product.reorder_level,
            "active": product.active,
            "archived_at": product.archived_at,
            "branch_id": branch.id,
            "branch_stock_qty": branch_stock_qty,
        }

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

    @staticmethod
    def _raise_product_conflict(
        conflict: Product,
        sku: str | None,
        barcode: str | None,
    ) -> None:
        if (
            barcode is not None
            and conflict.barcode is not None
            and conflict.barcode.strip() == barcode
        ):
            raise HTTPException(
                409,
                "Barcode already exists for this company",
            )
        raise HTTPException(409, "SKU already exists for this company")

    @staticmethod
    def _raise_barcode_integrity_error(error: IntegrityError) -> None:
        diagnostic = getattr(getattr(error, "orig", None), "diag", None)
        if (
            getattr(diagnostic, "constraint_name", None)
            == "uq_products_company_barcode_trimmed"
        ):
            raise HTTPException(
                409,
                "Barcode already exists for this company",
            ) from error
