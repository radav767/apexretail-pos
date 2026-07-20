from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException

from app.inventory.repository import InventoryRepository
from app.inventory.schema import (
    GRNCreate,
    StockAdjustmentCreate,
    StockTakeCreate,
)
from app.models.inventory_movement import InventoryMovement


class InventoryService:
    def __init__(self, repo: InventoryRepository):
        self.repo = repo

    async def receive_stock(self, data: GRNCreate):
        product = await self.repo.get_product_for_update(
            data.company_id,
            data.product_id,
        )

        if not product:
            raise HTTPException(404, "Product not found")

        before_qty = Decimal(product.stock_qty or 0)
        after_qty = before_qty + data.quantity

        if data.unit_cost is not None:
            product.cost_price = data.unit_cost

        product.stock_qty = after_qty

        movement = InventoryMovement(
            company_id=data.company_id,
            product_id=product.id,
            product_name=product.name,
            movement_type="grn",
            quantity=data.quantity,
            before_qty=before_qty,
            after_qty=after_qty,
            unit_cost=Decimal(product.cost_price or 0),
            reference=self._clean(data.reference),
            supplier=self._clean(data.supplier),
            notes=self._clean(data.notes),
        )

        return await self.repo.apply_movement(
            product,
            movement,
        )

    async def adjust_stock(
        self,
        data: StockAdjustmentCreate,
    ):
        product = await self.repo.get_product_for_update(
            data.company_id,
            data.product_id,
        )

        if not product:
            raise HTTPException(404, "Product not found")

        before_qty = Decimal(product.stock_qty or 0)

        if data.adjustment_type == "add":
            if data.quantity <= 0:
                raise HTTPException(
                    400,
                    "Add quantity must be greater than zero",
                )

            after_qty = before_qty + data.quantity

        elif data.adjustment_type == "remove":
            if data.quantity <= 0:
                raise HTTPException(
                    400,
                    "Remove quantity must be greater than zero",
                )

            if data.quantity > before_qty:
                raise HTTPException(
                    400,
                    "Cannot remove more than available stock",
                )

            after_qty = before_qty - data.quantity
        else:
            after_qty = data.quantity

        product.stock_qty = after_qty

        movement = InventoryMovement(
            company_id=data.company_id,
            product_id=product.id,
            product_name=product.name,
            movement_type=(
                f"adjustment_{data.adjustment_type}"
            ),
            quantity=abs(after_qty - before_qty),
            before_qty=before_qty,
            after_qty=after_qty,
            unit_cost=Decimal(product.cost_price or 0),
            reference=self._clean(data.reference),
            reason=data.reason.strip(),
            notes=self._clean(data.notes),
        )

        return await self.repo.apply_movement(
            product,
            movement,
        )

    async def stock_take(
        self,
        data: StockTakeCreate,
    ):
        seen_products = set()
        products = []
        movements = []

        for item in data.items:
            if item.product_id in seen_products:
                raise HTTPException(
                    400,
                    "The same product appears more than once",
                )

            seen_products.add(item.product_id)

            product = await self.repo.get_product_for_update(
                data.company_id,
                item.product_id,
            )

            if not product:
                raise HTTPException(
                    404,
                    f"Product not found: {item.product_id}",
                )

            before_qty = Decimal(product.stock_qty or 0)
            after_qty = item.physical_qty
            variance = after_qty - before_qty

            product.stock_qty = after_qty
            products.append(product)

            movements.append(
                InventoryMovement(
                    company_id=data.company_id,
                    product_id=product.id,
                    product_name=product.name,
                    movement_type="stock_take",
                    quantity=abs(variance),
                    before_qty=before_qty,
                    after_qty=after_qty,
                    unit_cost=Decimal(product.cost_price or 0),
                    reference=self._clean(data.reference),
                    reason="Physical stock count",
                    notes=self._clean(data.notes),
                )
            )

        return await self.repo.apply_movements(
            products,
            movements,
        )

    async def overview(self, company_id: UUID):
        products = await self.repo.list_overview(company_id)

        return [
            {
                "product_id": product.id,
                "name": product.name,
                "sku": product.sku,
                "unit": product.unit,
                "cost_price": product.cost_price,
                "selling_price": product.selling_price,
                "stock_qty": product.stock_qty,
                "reorder_level": product.reorder_level,
                "stock_value": (
                    Decimal(product.stock_qty or 0)
                    * Decimal(product.cost_price or 0)
                ),
                "low_stock": (
                    Decimal(product.stock_qty or 0)
                    <= Decimal(product.reorder_level or 0)
                ),
            }
            for product in products
        ]

    async def history(
        self,
        company_id: UUID,
        limit: int,
    ):
        return await self.repo.list_history(
            company_id,
            limit,
        )

    async def valuation(self, company_id: UUID):
        (
            total_products,
            total_quantity,
            total_cost_value,
            low_stock_products,
        ) = await self.repo.get_valuation(company_id)

        return {
            "total_products": total_products,
            "total_quantity": total_quantity,
            "total_cost_value": total_cost_value,
            "low_stock_products": low_stock_products,
        }

    @staticmethod
    def _clean(value: str | None):
        if value is None:
            return None

        cleaned = value.strip()
        return cleaned or None
