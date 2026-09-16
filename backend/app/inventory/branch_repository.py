from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch
from app.models.inventory_balance import InventoryBalance
from app.models.product import Product
from app.models.shop import Shop
from app.models.audit_event import AuditEvent


class BranchInventoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_branches(self, company_id: UUID):
        result = await self.db.execute(
            select(
                Branch.id,
                Branch.shop_id,
                Shop.name.label("shop_name"),
                Branch.name,
            )
            .join(Shop, Shop.id == Branch.shop_id)
            .where(
                Branch.company_id == company_id,
                Branch.active == True,
                Branch.deleted == False,
                Shop.active == True,
                Shop.deleted == False,
            )
            .order_by(
                Shop.name.asc(),
                Branch.name.asc(),
            )
        )

        return result.mappings().all()

    async def get_shop(
        self,
        company_id: UUID,
        shop_id: UUID | None,
    ):
        query = select(Shop).where(
            Shop.company_id == company_id,
            Shop.active == True,
            Shop.deleted == False,
        )

        if shop_id is not None:
            query = query.where(Shop.id == shop_id)

        result = await self.db.execute(
            query.order_by(Shop.created_at.asc()).limit(1)
        )

        return result.scalar_one_or_none()

    async def find_branch_name(
        self,
        company_id: UUID,
        shop_id: UUID,
        name: str,
    ):
        result = await self.db.execute(
            select(Branch).where(
                Branch.company_id == company_id,
                Branch.shop_id == shop_id,
                func.lower(Branch.name) == name.lower(),
                Branch.deleted == False,
            )
        )

        return result.scalar_one_or_none()

    async def create_branch(
        self,
        company_id: UUID,
        shop: Shop,
        name: str,
        *,
        actor=None,
    ):
        try:
            branch = Branch(
                company_id=company_id,
                shop_id=shop.id,
                name=name,
                active=True,
                deleted=False,
            )

            self.db.add(branch)
            await self.db.flush()

            product_result = await self.db.execute(
                select(Product).where(
                    Product.company_id == company_id,
                    Product.active == True,
                    Product.deleted == False,
                )
            )

            products = product_result.scalars().all()

            balances = [
                InventoryBalance(
                    company_id=company_id,
                    shop_id=shop.id,
                    branch_id=branch.id,
                    product_id=product.id,
                    quantity=Decimal("0"),
                    reorder_level=Decimal(
                        product.reorder_level or 0
                    ),
                    active=True,
                    deleted=False,
                )
                for product in products
            ]

            self.db.add_all(balances)
            if actor is not None:
                self.db.add(AuditEvent(
                    company_id=company_id,
                    actor_user_id=actor.user.id if actor.actor_type == "user" else None,
                    actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None,
                    action="terminal_branch_create",
                    details={
                        "branch_id": str(branch.id),
                        "shop_id": str(shop.id),
                        "branch_name": branch.name,
                    },
                ))
            await self.db.commit()
            await self.db.refresh(branch)

            return {
                "id": branch.id,
                "shop_id": shop.id,
                "shop_name": shop.name,
                "name": branch.name,
            }
        except Exception:
            await self.db.rollback()
            raise

    async def list_balances(
        self,
        company_id: UUID,
        branch_id: UUID | None,
    ):
        query = (
            select(
                InventoryBalance.branch_id,
                Branch.name.label("branch_name"),
                InventoryBalance.shop_id,
                Shop.name.label("shop_name"),
                Product.id.label("product_id"),
                Product.name.label("product_name"),
                Product.sku,
                Product.unit,
                InventoryBalance.quantity,
                InventoryBalance.reorder_level,
                Product.cost_price,
            )
            .join(
                Branch,
                Branch.id == InventoryBalance.branch_id,
            )
            .join(
                Shop,
                Shop.id == InventoryBalance.shop_id,
            )
            .join(
                Product,
                Product.id == InventoryBalance.product_id,
            )
            .where(
                InventoryBalance.company_id == company_id,
                InventoryBalance.active == True,
                InventoryBalance.deleted == False,
                Branch.active == True,
                Branch.deleted == False,
                Shop.active == True,
                Shop.deleted == False,
                Product.active == True,
                Product.deleted == False,
            )
        )

        if branch_id is not None:
            query = query.where(
                InventoryBalance.branch_id == branch_id,
            )

        result = await self.db.execute(
            query.order_by(
                Shop.name.asc(),
                Branch.name.asc(),
                Product.name.asc(),
            )
        )

        return result.mappings().all()
