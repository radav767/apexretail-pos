from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.inventory.stock_repository import BranchStockRepository
from app.models.inventory_movement import InventoryMovement
from app.models.product import Product


class InventoryRepository:
    def __init__(self, db: AsyncSession, *, commit_on_save: bool = True):
        self.db = db
        self.commit_on_save = commit_on_save
        self.stock = BranchStockRepository(db)

    async def resolve_branch(
        self,
        company_id: UUID,
        branch_id: UUID | None = None,
    ):
        return await self.stock.resolve_branch(
            company_id,
            branch_id,
        )

    async def get_product_for_update(
        self,
        company_id: UUID,
        product_id: UUID,
    ):
        return await self.stock.get_product_for_update(
            company_id,
            product_id,
        )

    async def get_balance_for_update(
        self,
        company_id: UUID,
        branch,
        product,
    ):
        return await self.stock.get_balance_for_update(
            company_id,
            branch,
            product,
        )

    async def sync_product_total(self, product):
        return await self.stock.sync_product_total(product)

    async def get_variant(self, company_id, product_id, variant_id):
        from .dimensions import variant_for_stock
        return await variant_for_stock(self.db, company_id, product_id, variant_id, include_inactive=True)

    async def get_variant_balance(self, company_id, branch, product, variant):
        from .dimensions import dimension_balance
        return await dimension_balance(self.db, self.stock, company_id, branch, product, variant)

    async def apply_movement(
        self,
        product,
        balance,
        movement: InventoryMovement,
    ):
        try:
            self.db.add(product)
            self.db.add(balance)
            self.db.add(movement)

            from app.business_operations.batches import allocate_batch_movements
            await allocate_batch_movements(self.db, [movement])
            if self.commit_on_save: await self.db.commit()
            else: await self.db.flush()
            await self.db.refresh(movement)

            return movement
        except Exception:
            await self.db.rollback()
            raise

    async def apply_movements(
        self,
        products,
        balances,
        movements,
    ):
        try:
            self.db.add_all(products)
            self.db.add_all(balances)
            self.db.add_all(movements)

            from app.business_operations.batches import allocate_batch_movements
            await allocate_batch_movements(self.db, movements)
            count_receipt = getattr(self, "count_receipt", None)
            if count_receipt is not None:
                count_receipt.details = {**count_receipt.details,"movement_ids":[str(m.id) for m in movements]}
                self.db.add(count_receipt)
            if self.commit_on_save: await self.db.commit()
            else: await self.db.flush()

            for movement in movements:
                await self.db.refresh(movement)

            return movements
        except Exception:
            await self.db.rollback()
            raise

    async def list_overview(self, company_id: UUID):
        result = await self.db.execute(
            select(Product)
            .where(
                Product.company_id == company_id,
                Product.active == True,
                Product.deleted == False,
            )
            .order_by(Product.name.asc())
        )

        return result.scalars().all()

    async def list_history(
        self,
        company_id: UUID,
        limit: int,
        branch_id=None,
    ):
        query = select(InventoryMovement).where(InventoryMovement.company_id == company_id)
        if branch_id is not None:
            query = query.where(InventoryMovement.branch_id == branch_id)
        result = await self.db.execute(
            query
            .order_by(InventoryMovement.created_at.desc())
            .limit(limit)
        )

        return result.scalars().all()

    async def get_valuation(self, company_id: UUID):
        from .valuation import stock_summary
        summary = await stock_summary(self.db, company_id)
        return (summary["total_products"], summary["total_quantity"], summary["stock_value"], summary["low_stock_products"])
