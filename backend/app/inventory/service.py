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
from app.models.audit_event import AuditEvent
from app.employees.manager_approval import consume_manager_authorization
from app.employees.permissions import has_permission


LEGACY_GRN_REASON = "Stock received - legacy client"


class InventoryService:
    def __init__(self, repo: InventoryRepository):
        self.repo = repo

    async def receive_stock(self, data: GRNCreate, actor=None):
        data = data.model_copy()
        if hasattr(self.repo, "authorize_command"):
            await self.repo.authorize_command(data, actor, "inventory_receive", new=True)
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

        received_unit = self._clean(data.received_unit)
        base_quantity = Decimal(data.quantity)
        conversion_factor = Decimal("1")
        if received_unit:
            purchase_unit = str(getattr(product, "purchase_unit", "") or "").strip().lower()
            if not purchase_unit or received_unit.lower() != purchase_unit:
                raise HTTPException(400, "Received unit does not match the product purchase unit")
            conversion_factor = Decimal(getattr(product, "units_per_purchase", 1) or 1)
            base_quantity = (Decimal(data.quantity) * conversion_factor).quantize(Decimal("0.001"))

        before_qty = Decimal(balance.quantity or 0)
        after_qty = before_qty + base_quantity

        balance.quantity = after_qty

        if data.unit_cost is not None:
            product.cost_price = (
                Decimal(data.unit_cost) / conversion_factor
            ).quantize(Decimal("0.01"))

        await self.repo.sync_product_total(product)

        movement = InventoryMovement(
            company_id=data.company_id,
            shop_id=branch.shop_id,
            branch_id=branch.id,
            product_id=product.id,
            product_name=product.name,
            movement_type="grn",
            quantity=base_quantity,
            before_qty=before_qty,
            after_qty=after_qty,
            unit_cost=Decimal(product.cost_price or 0),
            reference=self._clean(data.reference),
            supplier=self._clean(data.supplier),
            reason=self._clean_reason(data.reason),
            notes=(
                f"{data.quantity} {received_unit} converted to {base_quantity} {product.unit}. "
                f"{self._clean(data.notes) or ''}"
            ).strip()
            if received_unit
            else self._clean(data.notes),
        )

        return await self.repo.apply_movement(
            product,
            balance,
            movement,
        )

    async def adjust_stock(
        self,
        data: StockAdjustmentCreate,
        actor=None,
    ):
        data = data.model_copy()
        if hasattr(self.repo, "authorize_command"):
            await self.repo.authorize_command(data, actor, new=True)
        if actor is not None and actor.actor_type == "employee" and not has_permission(actor.permissions, "inventory_adjust"):
            await consume_manager_authorization(
                self.repo.db, actor, data.manager_authorization_token,
                "stock_adjustment", {
                    "product_id": str(data.product_id),
                    "branch_id": str(data.branch_id or actor.employee.branch_id),
                    "adjustment_type": data.adjustment_type,
                    "quantity": str(data.quantity),
                },
            )
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
        self.repo.db.add(AuditEvent(
            company_id=data.company_id,
            actor_employee_id=actor.employee.id if actor and actor.actor_type == "employee" else None,
            actor_user_id=actor.user.id if actor and actor.actor_type == "user" else None,
            device_id=actor.pos_session.device_id if actor and actor.actor_type == "employee" and actor.pos_session else None,
            action="inventory_adjustment",
            reason=data.reason.strip(),
            details={
                "product_id": str(product.id), "branch_id": str(branch.id),
                "before_qty": str(before_qty), "after_qty": str(after_qty),
                "adjustment_type": data.adjustment_type,
            },
        ))

        return await self.repo.apply_movement(
            product,
            balance,
            movement,
        )

    async def stock_take(
        self,
        data: StockTakeCreate,
        actor=None,
    ):
        data = data.model_copy()
        if hasattr(self.repo, "authorize_command"):
            await self.repo.authorize_command(data, actor, "inventory_count")
        if data.request_id is not None:
            from .count_requests import prepare_count
            replay, self.repo.count_receipt = await prepare_count(self.repo.db, data, actor)
            if replay is not None:return replay
        elif hasattr(self.repo, "count_receipt"):
            self.repo.count_receipt=None
        if hasattr(self.repo, "authorize_command"):
            await self.repo.authorize_command(data, actor, "inventory_count", new=True)
        branch = await self.repo.resolve_branch(
            data.company_id,
            data.branch_id,
        )

        seen_products = set()
        products = []
        balances = []
        movements = []

        for item in sorted(data.items,key=lambda row:(str(row.product_id),str(row.variant_id or ""))):
            dimension=(item.product_id,item.variant_id)
            if dimension in seen_products:
                raise HTTPException(
                    400,
                    "The same product appears more than once",
                )

            seen_products.add(dimension)

            product = await self.repo.get_product_for_update(
                data.company_id,
                item.product_id,
            )

            variant = await self.repo.get_variant(data.company_id, product.id, item.variant_id) if item.variant_id else None
            balance = await self.repo.get_variant_balance(data.company_id, branch, product, variant) if variant else await self.repo.get_balance_for_update(data.company_id, branch, product)

            before_qty = Decimal(balance.quantity or 0)
            after_qty = item.physical_qty
            variance = after_qty - before_qty

            if data.request_id is not None and item.expected_qty is None:
                raise HTTPException(422,"A protected count requires its original system quantity")
            if item.expected_qty is not None and item.expected_qty != before_qty:
                raise HTTPException(409,"Stock changed since counting started. Original count retained; review current stock")
            if variance and hasattr(self.repo,"db") and not hasattr(self.repo,"batch"):
                from sqlalchemy import select
                from app.models import ProductBatch
                tracked=(await self.repo.db.execute(select(ProductBatch.id).where(ProductBatch.company_id==data.company_id,
                    ProductBatch.product_id==product.id,ProductBatch.branch_id==branch.id,ProductBatch.variant_id==item.variant_id).limit(1))).first()
                if tracked:raise HTTPException(409,"Count each selected batch to preserve batch numbers and expiry dates")

            balance.quantity = after_qty
            if variant is None:await self.repo.sync_product_total(product)

            products.append(product)
            balances.append(balance)

            movements.append(
                InventoryMovement(
                    company_id=data.company_id,
                    shop_id=branch.shop_id,
                    branch_id=branch.id,
                    product_id=product.id,
                    variant_id=item.variant_id,
                    product_name=f"{product.name} — {variant.name}" if variant else product.name,
                    movement_type="stock_take",
                    quantity=abs(variance),
                    before_qty=before_qty,
                    after_qty=after_qty,
                    unit_cost=Decimal(
                        (variant.cost_price if variant and variant.cost_price is not None else product.cost_price) or 0
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
                "purchase_unit": getattr(product, "purchase_unit", None),
                "units_per_purchase": Decimal(
                    getattr(product, "units_per_purchase", 1) or 1
                ),
                "cost_price": product.cost_price,
                "selling_price": product.selling_price,
                "stock_qty": product.stock_qty,
                "reorder_level": product.reorder_level,
                "stock_value": (
                    Decimal(product.stock_qty or 0) * Decimal(product.cost_price)
                    if product.cost_price is not None else None
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
        actor=None,
    ):
        if actor is not None and actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            return await self.repo.list_history(company_id, limit, branch_id=actor.employee.branch_id)
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
