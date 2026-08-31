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


LEGACY_GRN_REASON = "Stock received - legacy client"


class InventoryService:
    def __init__(self, repo: InventoryRepository):
        self.repo = repo

    async def receive_stock(self, data: GRNCreate):
        branch = await self.repo.resolve_branch(
            data.company_id,
            data.branch_id,
        )

        product = await self.repo.get_product_for_update(
            data.company_id,
            data.product_id,
        )

        balance = await self.repo.get_balance_for_update(
            data.company_id,
            branch,
            product,
        )

        before_qty = Decimal(balance.quantity or 0)
        after_qty = before_qty + data.quantity

        balance.quantity = after_qty

        if data.unit_cost is not None:
            product.cost_price = data.unit_cost

        await self.repo.sync_product_total(product)

        movement = InventoryMovement(
            company_id=data.company_id,
            shop_id=branch.shop_id,
            branch_id=branch.id,
            product_id=product.id,
            product_name=product.name,
            movement_type="grn",
            quantity=data.quantity,
            before_qty=before_qty,
            after_qty=after_qty,
            unit_cost=Decimal(product.cost_price or 0),
            reference=self._clean(data.reference),
            supplier=self._clean(data.supplier),
            reason=self._clean_reason(data.reason),
            notes=self._clean(data.notes),
        )

        return await self.repo.apply_movement(
            product,
            balance,
            movement,
        )

    async def adjust_stock(
        self,
        data: StockAdjustmentCreate,
    ):
        branch = await self.repo.resolve_branch(
            data.company_id,
            data.branch_id,
        )

        product = await self.repo.get_product_for_update(
            data.company_id,
            data.product_id,
        )

        balance = await self.repo.get_balance_for_update(
            data.company_id,
            branch,
            product,
        )

        before_qty = Decimal(balance.quantity or 0)

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
                    "Cannot remove more than branch stock",
                )

            after_qty = before_qty - data.quantity

        else:
            after_qty = data.quantity

        balance.quantity = after_qty
        await self.repo.sync_product_total(product)

        movement = InventoryMovement(
            company_id=data.company_id,
            shop_id=branch.shop_id,
            branch_id=branch.id,
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
            balance,
            movement,
        )

    async def stock_take(
        self,
        data: StockTakeCreate,
    ):
        branch = await self.repo.resolve_branch(
            data.company_id,
            data.branch_id,
        )

        seen_products = set()
        products = []
        balances = []
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

            balance = await self.repo.get_balance_for_update(
                data.company_id,
                branch,
                product,
            )

            before_qty = Decimal(balance.quantity or 0)
            after_qty = item.physical_qty
            variance = after_qty - before_qty

            balance.quantity = after_qty
            await self.repo.sync_product_total(product)

            products.append(product)
            balances.append(balance)

            movements.append(
                InventoryMovement(
                    company_id=data.company_id,
                    shop_id=branch.shop_id,
                    branch_id=branch.id,
                    product_id=product.id,
                    product_name=product.name,
                    movement_type="stock_take",
                    quantity=abs(variance),
                    before_qty=before_qty,
                    after_qty=after_qty,
                    unit_cost=Decimal(
                        product.cost_price or 0
                    ),
                    reference=self._clean(data.reference),
                    reason="Physical stock count",
                    notes=self._clean(data.notes),
                )
            )

        return await self.repo.apply_movements(
            products,
            balances,
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

    @classmethod
    def _clean_reason(
        cls,
        value: str | None,
    ) -> str:
        cleaned = cls._clean(value)
        return cleaned or LEGACY_GRN_REASON
