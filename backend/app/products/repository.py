from decimal import Decimal
from uuid import UUID
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.inventory.stock_repository import BranchStockRepository
from app.models.branch import Branch
from app.models.category import Category
from app.models.inventory_balance import InventoryBalance
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product
from app.models.product_component import ProductComponent
from app.models.product_variant import ProductVariant
from app.models.product_media import ProductMedia
from app.models.variant_inventory_balance import VariantInventoryBalance
from app.models.product_price_level import ProductPriceLevel
from app.models.product_creation_request import (
    ProductCreationRequest,
)
from app.models.shop import Shop


class ProductRepository:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.stock = BranchStockRepository(db)

    async def require_write(self, company_id, *, features=()):
        from app.subscriptions.write_policy import require_new_write
        return await require_new_write(self.db, company_id, features=features)

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
    async def get_category_by_name(self,company_id,name):
        return (await self.db.execute(select(Category).where(Category.company_id==company_id,func.lower(Category.name)==name.strip().lower(),Category.deleted==False))).scalar_one_or_none()

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
        await self.db.commit()
        return category

    async def category_dependency_counts(
        self,
        company_id: UUID,
        category_id: UUID,
    ) -> tuple[int, int]:
        product_result = await self.db.execute(
            select(func.count(Product.id)).where(
                Product.company_id == company_id,
                Product.category_id == category_id,
                Product.deleted == False,
            )
        )
        child_result = await self.db.execute(
            select(func.count(Category.id)).where(
                Category.company_id == company_id,
                Category.parent_id == category_id,
                Category.deleted == False,
            )
        )
        return int(product_result.scalar_one() or 0), int(child_result.scalar_one() or 0)

    async def resolve_branch(
        self,
        company_id: UUID,
        branch_id: UUID | None = None,
    ) -> Branch:
        return await self.stock.resolve_branch(
            company_id,
            branch_id,
        )

    async def list_active_branches(self, company_id: UUID):
        result = await self.db.execute(
            select(Branch)
            .join(Shop, Shop.id == Branch.shop_id)
            .where(
                Branch.company_id == company_id,
                Branch.active == True,
                Branch.deleted == False,
                Shop.company_id == company_id,
                Shop.active == True,
                Shop.deleted == False,
            )
            .order_by(
                Shop.created_at.asc(),
                Branch.created_at.asc(),
            )
        )
        return result.scalars().all()

    async def create_product(
        self,
        product: Product,
        *,
        opening_quantity: Decimal,
        branch_id: UUID | None,
    ):
        try:
            self.db.add(product)
            await self.db.flush()

            branches = await self.list_active_branches(
                product.company_id
            )

            if opening_quantity > 0 and not branches:
                raise HTTPException(
                    400,
                    "Create a branch before adding opening stock",
                )

            target_branch = None

            if branch_id is not None:
                target_branch = next(
                    (
                        branch
                        for branch in branches
                        if branch.id == branch_id
                    ),
                    None,
                )

            if target_branch is None and opening_quantity > 0:
                target_branch = branches[0]

            if target_branch is not None:
                self.db.add(
                    InventoryBalance(
                        company_id=product.company_id,
                        shop_id=target_branch.shop_id,
                        branch_id=target_branch.id,
                        product_id=product.id,
                        quantity=opening_quantity,
                        reorder_level=Decimal(
                            product.reorder_level or 0
                        ),
                        active=True,
                        deleted=False,
                    )
                )
                await self.stock.sync_product_total(product)
            else:
                product.stock_qty = Decimal("0")
                self.db.add(product)

            if (
                opening_quantity > 0
                and target_branch is not None
            ):
                self.db.add(
                    InventoryMovement(
                        company_id=product.company_id,
                        shop_id=target_branch.shop_id,
                        branch_id=target_branch.id,
                        product_id=product.id,
                        product_name=product.name,
                        movement_type="opening_stock",
                        quantity=opening_quantity,
                        before_qty=Decimal("0"),
                        after_qty=opening_quantity,
                        unit_cost=Decimal(
                            product.cost_price or 0
                        ),
                        reason="Product opening stock",
                        notes=(
                            "Opening quantity recorded during "
                            "product creation"
                        ),
                    )
                )

            if product.create_request_key:
                self.db.add(
                    ProductCreationRequest(
                        company_id=product.company_id,
                        product_id=product.id,
                        idempotency_key=product.create_request_key,
                        active=True,
                        deleted=False,
                    )
                )

            await self.db.commit()
            await self.db.refresh(product)
            return product
        except IntegrityError:
            await self.db.rollback()
            raise
        except Exception:
            await self.db.rollback()
            raise

    async def list_products(
        self,
        company_id: UUID,
        *,
        search: str | None = None,
        category_id: UUID | None = None,
        product_type: str | None = None,
    ):
        query = select(Product).where(
                Product.company_id == company_id,
                Product.deleted == False,
            )
        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Product.name.ilike(pattern),
                    Product.sku.ilike(pattern),
                    Product.barcode.ilike(pattern),
                )
            )
        if category_id is not None:
            query = query.where(Product.category_id == category_id)
        if product_type:
            query = query.where(Product.product_type == product_type)
        result = await self.db.execute(query.order_by(Product.name.asc()))
        return result.scalars().all()

    async def product_is_component(self, company_id: UUID, product_id: UUID) -> bool:
        result = await self.db.execute(
            select(func.count(ProductComponent.id)).where(
                ProductComponent.company_id == company_id,
                ProductComponent.component_product_id == product_id,
                ProductComponent.active == True,
                ProductComponent.deleted == False,
            )
        )
        return bool(result.scalar_one())

    async def list_components(self, company_id: UUID, composite_product_id: UUID):
        result = await self.db.execute(
            select(ProductComponent, Product)
            .join(Product, Product.id == ProductComponent.component_product_id)
            .where(
                ProductComponent.company_id == company_id,
                ProductComponent.composite_product_id == composite_product_id,
                ProductComponent.active == True,
                ProductComponent.deleted == False,
                Product.company_id == company_id,
                Product.deleted == False,
            )
            .order_by(Product.name.asc())
        )
        return result.all()

    async def replace_components(
        self,
        company_id: UUID,
        composite_product_id: UUID,
        components: list[dict],
    ):
        result = await self.db.execute(
            select(ProductComponent).where(
                ProductComponent.company_id == company_id,
                ProductComponent.composite_product_id == composite_product_id,
            )
        )
        existing = {row.component_product_id: row for row in result.scalars().all()}
        requested_ids = {row["component_product_id"] for row in components}
        for component_id, row in existing.items():
            if component_id not in requested_ids:
                row.active = False
                row.deleted = True
        for values in components:
            row = existing.get(values["component_product_id"])
            if row is None:
                row = ProductComponent(
                    company_id=company_id,
                    composite_product_id=composite_product_id,
                    **values,
                )
            else:
                row.quantity = values["quantity"]
                row.unit = values["unit"]
                row.active = True
                row.deleted = False
            self.db.add(row)
        await self.db.commit()
        return await self.list_components(company_id, composite_product_id)

    async def list_variants(self, company_id: UUID, product_id: UUID | None = None, branch_id: UUID | None = None):
        query = select(ProductVariant,VariantInventoryBalance).outerjoin(VariantInventoryBalance,(VariantInventoryBalance.variant_id==ProductVariant.id)&(VariantInventoryBalance.branch_id==branch_id)&(VariantInventoryBalance.deleted==False)).where(
            ProductVariant.company_id == company_id,
            ProductVariant.deleted == False,
        )
        if product_id is not None:
            query = query.where(ProductVariant.product_id == product_id)
        result = await self.db.execute(query.order_by(ProductVariant.name.asc()))
        return result.all()

    async def get_variant_balance(self,company_id,branch,product_id,variant_id):
        row=(await self.db.execute(select(VariantInventoryBalance).where(VariantInventoryBalance.company_id==company_id,VariantInventoryBalance.branch_id==branch.id,VariantInventoryBalance.variant_id==variant_id,VariantInventoryBalance.deleted==False).with_for_update())).scalar_one_or_none()
        if row is None:
            row=VariantInventoryBalance(company_id=company_id,shop_id=branch.shop_id,branch_id=branch.id,product_id=product_id,variant_id=variant_id,quantity=0,reorder_level=0); self.db.add(row); await self.db.flush()
        return row

    async def get_variant(self, company_id: UUID, variant_id: UUID):
        result = await self.db.execute(
            select(ProductVariant).where(
                ProductVariant.id == variant_id,
                ProductVariant.company_id == company_id,
                ProductVariant.deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def save_variant(self, variant: ProductVariant):
        self.db.add(variant)
        await self.db.commit()
        await self.db.refresh(variant)
        return variant
    async def get_media(self,company_id,media_id):
        return (await self.db.execute(select(ProductMedia).where(ProductMedia.company_id==company_id,ProductMedia.id==media_id))).scalar_one_or_none()

    async def list_price_levels(self, company_id: UUID, product_id: UUID | None = None):
        query = select(ProductPriceLevel).where(
            ProductPriceLevel.company_id == company_id,
            ProductPriceLevel.deleted == False,
        )
        if product_id is not None:
            query = query.where(ProductPriceLevel.product_id == product_id)
        result = await self.db.execute(
            query.order_by(ProductPriceLevel.name.asc(), ProductPriceLevel.minimum_quantity.asc())
        )
        return result.scalars().all()

    async def get_price_level(self, company_id: UUID, price_level_id: UUID):
        result = await self.db.execute(
            select(ProductPriceLevel).where(
                ProductPriceLevel.id == price_level_id,
                ProductPriceLevel.company_id == company_id,
                ProductPriceLevel.deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def save_price_level(self, price_level: ProductPriceLevel):
        self.db.add(price_level)
        await self.db.commit()
        await self.db.refresh(price_level)
        return price_level

    async def get_product(self, company_id: UUID, product_id: UUID):
        result = await self.db.execute(
            select(Product).where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.deleted == False,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_create_request_key(
        self,
        company_id: UUID,
        create_request_key: str,
    ):
        result = await self.db.execute(
            select(Product)
            .join(
                ProductCreationRequest,
                ProductCreationRequest.product_id == Product.id,
            )
            .where(
                Product.company_id == company_id,
                Product.deleted == False,
                ProductCreationRequest.company_id == company_id,
                ProductCreationRequest.idempotency_key
                == create_request_key,
                ProductCreationRequest.deleted == False,
            )
            .limit(1)
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
            conditions.append(func.btrim(Product.barcode) == barcode)

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

    async def find_active_by_barcode(
        self,
        company_id: UUID,
        barcode: str,
    ):
        result = await self.db.execute(
            select(Product).where(
                Product.company_id == company_id,
                Product.active == True,
                Product.deleted == False,
                func.btrim(Product.barcode) == barcode,
            )
        )
        return result.scalar_one_or_none()

    async def get_branch_stock_quantity(
        self,
        company_id: UUID,
        branch_id: UUID,
        product_id: UUID,
    ) -> Decimal:
        result = await self.db.execute(
            select(InventoryBalance.quantity).where(
                InventoryBalance.company_id == company_id,
                InventoryBalance.branch_id == branch_id,
                InventoryBalance.product_id == product_id,
                InventoryBalance.active == True,
                InventoryBalance.deleted == False,
            )
        )
        return Decimal(result.scalar_one_or_none() or 0)

    async def update_product(self, product: Product, changes: dict):
        try:
            reorder_level_changed = "reorder_level" in changes

            for field, value in changes.items():
                setattr(product, field, value)

            if reorder_level_changed:
                await self.db.execute(
                    update(InventoryBalance)
                    .where(
                        InventoryBalance.company_id
                        == product.company_id,
                        InventoryBalance.product_id == product.id,
                        InventoryBalance.deleted == False,
                    )
                    .values(
                        reorder_level=Decimal(
                            product.reorder_level or 0
                        )
                    )
                )

            self.db.add(product)
            await self.db.commit()
            await self.db.refresh(product)
            return product
        except Exception:
            await self.db.rollback()
            raise

    async def delete_product(self, product: Product):
        product.active = False
        product.archived_at = datetime.now(timezone.utc)

        await self.db.execute(
            update(InventoryBalance)
            .where(
                InventoryBalance.company_id == product.company_id,
                InventoryBalance.product_id == product.id,
                InventoryBalance.deleted == False,
            )
            .values(
                active=False,
                deleted=False,
            )
        )

        await self.db.commit()
        return product
