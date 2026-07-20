from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_movement import InventoryMovement
from app.models.product import Product


class InventoryRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_product_for_update(
        self,
        company_id: UUID,
        product_id: UUID,
    ):
        result = await self.db.execute(
            select(Product)
            .where(
                Product.id == product_id,
                Product.company_id == company_id,
                Product.deleted == False,
            )
            .with_for_update()
        )

        return result.scalar_one_or_none()

    async def apply_movement(
        self,
        product: Product,
        movement: InventoryMovement,
    ):
        try:
            self.db.add(movement)

            await self.db.commit()
            await self.db.refresh(product)
            await self.db.refresh(movement)

            return movement
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
    ):
        result = await self.db.execute(
            select(InventoryMovement)
            .where(
                InventoryMovement.company_id == company_id,
            )
            .order_by(InventoryMovement.created_at.desc())
            .limit(limit)
        )

        return result.scalars().all()

    async def get_valuation(self, company_id: UUID):
        result = await self.db.execute(
            select(
                func.count(Product.id),
                func.coalesce(func.sum(Product.stock_qty), 0),
                func.coalesce(
                    func.sum(
                        Product.stock_qty * Product.cost_price
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                Product.stock_qty
                                <= Product.reorder_level,
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(
                Product.company_id == company_id,
                Product.active == True,
                Product.deleted == False,
            )
        )

        return result.one()
