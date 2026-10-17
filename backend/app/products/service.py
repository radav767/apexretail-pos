import uuid
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.category import Category
from app.models.product import Product
from app.models.product_variant import ProductVariant
from app.models.product_price_level import ProductPriceLevel
from app.models.audit_event import AuditEvent
from app.products.repository import ProductRepository
from app.products.schema import (
    CategoryCreate,
    CategoryUpdate,
    ProductCreate,
    ProductComponentWrite,
    ProductImportRequest,
    ProductPriceLevelCreate,
    ProductPriceLevelUpdate,
    ProductUpdate,
    ProductVariantCreate,
    ProductVariantUpdate,
)


class ProductService:
    def __init__(self, repo: ProductRepository):
        self.repo = repo

    async def create_category(self, data: CategoryCreate):
        name = data.name.strip()

        await self._validate_category_parent(
            data.company_id,
            data.parent_id,
        )

        duplicate = await self.repo.find_category_by_name(
            data.company_id,
            name,
        )

        if duplicate:
            raise HTTPException(409, "Category already exists")

        category = Category(
            company_id=data.company_id,
            parent_id=data.parent_id,
            name=name,
            image_url=self._clean_optional(data.image_url),
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

        if "parent_id" in changes:
            if changes["parent_id"] == category_id:
                raise HTTPException(400, "A category cannot be its own parent")
            await self._validate_category_parent(company_id, changes["parent_id"])
            ancestor_id = changes["parent_id"]
            visited = {category_id}
            while ancestor_id is not None:
                if ancestor_id in visited:
                    raise HTTPException(400, "Category hierarchy cannot contain a cycle")
                visited.add(ancestor_id)
                ancestor = await self.repo.get_category(company_id, ancestor_id)
                ancestor_id = ancestor.parent_id if ancestor else None

        if "image_url" in changes:
            changes["image_url"] = self._clean_optional(changes["image_url"])

        return await self.repo.update_category(category, changes)

    async def delete_category(
        self,
        company_id: UUID,
        category_id: UUID,
    ):
        category = await self.repo.get_category(company_id, category_id)

        if not category:
            raise HTTPException(404, "Category not found")

        product_count, child_count = await self.repo.category_dependency_counts(
            company_id,
            category_id,
        )
        if product_count or child_count:
            raise HTTPException(
                409,
                "Category cannot be deleted while products or child categories depend on it",
            )

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
        values["purchase_unit"] = self._clean_optional(values.get("purchase_unit"))
        values["image_url"] = self._clean_optional(values.get("image_url"))
        values["sku"] = self._clean_optional(values.get("sku"))
        values["barcode"] = self._clean_optional(values.get("barcode"))

        if values["sku"] is None:
            values["sku"] = f"APR-{uuid.uuid4().hex[:10].upper()}"

        if values["product_type"] in {"service", "non_stock"}:
            values["track_inventory"] = False
            opening_quantity = Decimal("0")
        elif values["product_type"] in {"composite", "bundle"}:
            values["track_inventory"] = False
            opening_quantity = Decimal("0")

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

    async def list_products(
        self,
        company_id: UUID,
        *,
        search: str | None = None,
        category_id: UUID | None = None,
        product_type: str | None = None,
        include_cost: bool = True,
    ):
        products = await self.repo.list_products(
            company_id,
            search=search,
            category_id=category_id,
            product_type=product_type,
        )
        if include_cost:
            return products
        return [
            {
                "id": product.id,
                "company_id": product.company_id,
                "category_id": product.category_id,
                "name": product.name,
                "sku": product.sku,
                "barcode": product.barcode,
                "product_type": product.product_type,
                "image_url": product.image_url,
                "unit": product.unit,
                "purchase_unit": product.purchase_unit,
                "units_per_purchase": product.units_per_purchase,
                "track_inventory": product.track_inventory,
                "tax_rate": product.tax_rate,
                "tax_exempt": product.tax_exempt,
                "cost_price": None,
                "selling_price": product.selling_price,
                "stock_qty": product.stock_qty,
                "reorder_level": product.reorder_level,
                "active": product.active,
                "archived_at": product.archived_at,
            }
            for product in products
        ]

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

        for optional_field in ("purchase_unit", "image_url"):
            if optional_field in changes:
                changes[optional_field] = self._clean_optional(changes[optional_field])

        resulting_type = changes.get("product_type", product.product_type)
        if resulting_type in {"service", "non_stock", "composite", "bundle"}:
            changes["track_inventory"] = False

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
            "product_type": product.product_type,
            "image_url": product.image_url,
            "unit": product.unit,
            "purchase_unit": product.purchase_unit,
            "units_per_purchase": product.units_per_purchase,
            "track_inventory": product.track_inventory,
            "tax_rate": product.tax_rate,
            "tax_exempt": product.tax_exempt,
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

        if (
            hasattr(self.repo, "product_is_component")
            and await self.repo.product_is_component(company_id, product_id)
        ):
            raise HTTPException(
                409,
                "Product cannot be archived while it is used by an active composite product",
            )

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

    async def list_components(self, company_id: UUID, product_id: UUID):
        product = await self.repo.get_product(company_id, product_id)
        if not product:
            raise HTTPException(404, "Product not found")
        rows = await self.repo.list_components(company_id, product_id)
        return [self._component_out(component, item) for component, item in rows]

    async def replace_components(
        self,
        company_id: UUID,
        product_id: UUID,
        data: list[ProductComponentWrite],
    ):
        product = await self.repo.get_product(company_id, product_id)
        if not product:
            raise HTTPException(404, "Product not found")
        if product.product_type not in {"composite", "bundle"}:
            raise HTTPException(400, "Components require a composite or bundle product")
        if not data:
            raise HTTPException(400, "At least one component is required")
        component_ids = [item.component_product_id for item in data]
        if len(set(component_ids)) != len(component_ids):
            raise HTTPException(400, "Each component product may appear only once")
        values = []
        for item in data:
            if item.component_product_id == product_id:
                raise HTTPException(400, "A product cannot contain itself")
            component = await self.repo.get_product(company_id, item.component_product_id)
            if not component or not component.active:
                raise HTTPException(400, "Component product is missing or inactive")
            if component.product_type in {"composite", "bundle"}:
                raise HTTPException(400, "Nested composite products are not supported")
            if not component.track_inventory:
                raise HTTPException(400, "Components must be inventory-tracked products")
            values.append(
                {
                    "component_product_id": item.component_product_id,
                    "quantity": item.quantity,
                    "unit": item.unit.strip().lower(),
                }
            )
        rows = await self.repo.replace_components(company_id, product_id, values)
        total_cost = sum(
            (Decimal(item.cost_price or 0) * Decimal(component.quantity) for component, item in rows),
            Decimal("0"),
        ).quantize(Decimal("0.01"))
        await self.repo.update_product(product, {"cost_price": total_cost})
        return [self._component_out(component, item) for component, item in rows]

    async def list_variants(self, company_id: UUID, product_id: UUID | None):
        return await self.repo.list_variants(company_id, product_id)

    async def create_variant(self, company_id: UUID, product_id: UUID, data: ProductVariantCreate):
        await self._require_product(company_id, product_id)
        variant = ProductVariant(
            company_id=company_id,
            product_id=product_id,
            **data.model_dump(),
            active=True,
            deleted=False,
        )
        try:
            return await self.repo.save_variant(variant)
        except IntegrityError as error:
            raise HTTPException(409, "Variant SKU or barcode already exists") from error

    async def update_variant(self, company_id: UUID, variant_id: UUID, data: ProductVariantUpdate):
        variant = await self.repo.get_variant(company_id, variant_id)
        if not variant:
            raise HTTPException(404, "Variant not found")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(variant, field, value.strip() if isinstance(value, str) else value)
        try:
            return await self.repo.save_variant(variant)
        except IntegrityError as error:
            raise HTTPException(409, "Variant SKU or barcode already exists") from error

    async def delete_variant(self, company_id: UUID, variant_id: UUID):
        variant = await self.repo.get_variant(company_id, variant_id)
        if not variant:
            raise HTTPException(404, "Variant not found")
        variant.active = False
        variant.deleted = True
        await self.repo.save_variant(variant)
        return {"ok": True, "message": "Variant archived"}

    async def list_price_levels(self, company_id: UUID, product_id: UUID | None):
        return await self.repo.list_price_levels(company_id, product_id)

    async def create_price_level(self, company_id: UUID, product_id: UUID, data: ProductPriceLevelCreate):
        await self._require_product(company_id, product_id)
        level = ProductPriceLevel(
            company_id=company_id,
            product_id=product_id,
            **data.model_dump(),
            active=True,
            deleted=False,
        )
        try:
            return await self.repo.save_price_level(level)
        except IntegrityError as error:
            raise HTTPException(409, "Price level name already exists for this product") from error

    async def update_price_level(self, company_id: UUID, price_level_id: UUID, data: ProductPriceLevelUpdate):
        level = await self.repo.get_price_level(company_id, price_level_id)
        if not level:
            raise HTTPException(404, "Price level not found")
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(level, field, value.strip() if isinstance(value, str) else value)
        return await self.repo.save_price_level(level)

    async def delete_price_level(self, company_id: UUID, price_level_id: UUID):
        level = await self.repo.get_price_level(company_id, price_level_id)
        if not level:
            raise HTTPException(404, "Price level not found")
        level.active = False
        level.deleted = True
        await self.repo.save_price_level(level)
        return {"ok": True, "message": "Price level archived"}

    async def import_products(self, data: ProductImportRequest, actor=None):
        created = []
        for row in data.rows:
            created.append(
                await self.create_product(
                    ProductCreate(
                        company_id=data.company_id,
                        branch_id=data.branch_id,
                        create_request_key=f"import-{uuid.uuid4()}",
                        stock_qty=Decimal("0"),
                        **row.model_dump(),
                    )
                )
            )
        return created

    async def _require_product(self, company_id: UUID, product_id: UUID):
        product = await self.repo.get_product(company_id, product_id)
        if not product:
            raise HTTPException(404, "Product not found")
        return product

    async def _validate_category_parent(self, company_id: UUID, parent_id: UUID | None):
        if parent_id is None:
            return
        parent = await self.repo.get_category(company_id, parent_id)
        if not parent or not parent.active:
            raise HTTPException(400, "Parent category is missing or inactive")

    @staticmethod
    def _component_out(component, product):
        component_cost = Decimal(product.cost_price or 0)
        return {
            "id": component.id,
            "company_id": component.company_id,
            "composite_product_id": component.composite_product_id,
            "component_product_id": component.component_product_id,
            "component_name": product.name,
            "quantity": component.quantity,
            "unit": component.unit,
            "component_cost": component_cost,
            "total_cost": (component_cost * Decimal(component.quantity)).quantize(Decimal("0.01")),
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
