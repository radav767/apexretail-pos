import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from app.inventory.transfer_repository import TransferRepository
from app.inventory.transfer_schema import TransferCreate
from app.models.inventory_movement import InventoryMovement


class TransferService:
    def __init__(self, repo: TransferRepository):
        self.repo = repo

    async def transfer(self, data: TransferCreate):
        if data.source_branch_id == data.destination_branch_id:
            raise HTTPException(
                400,
                "Source and destination branches must be different",
            )

        source_branch = await self.repo.resolve_branch(
            data.company_id,
            data.source_branch_id,
        )

        destination_branch = await self.repo.resolve_branch(
            data.company_id,
            data.destination_branch_id,
        )

        reference = self._clean(data.reference)

        if not reference:
            reference = (
                f"TRF-{datetime.now(timezone.utc):%Y%m%d}-"
                f"{str(uuid.uuid4())[:8].upper()}"
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

            product = await self.repo.get_product(
                data.company_id,
                item.product_id,
            )

            if str(source_branch.id) < str(destination_branch.id):
                source_balance = await self.repo.get_balance(
                    data.company_id,
                    source_branch,
                    product,
                )

                destination_balance = await self.repo.get_balance(
                    data.company_id,
                    destination_branch,
                    product,
                )
            else:
                destination_balance = await self.repo.get_balance(
                    data.company_id,
                    destination_branch,
                    product,
                )

                source_balance = await self.repo.get_balance(
                    data.company_id,
                    source_branch,
                    product,
                )

            source_before = Decimal(
                source_balance.quantity or 0
            )

            destination_before = Decimal(
                destination_balance.quantity or 0
            )

            if item.quantity > source_before:
                raise HTTPException(
                    400,
                    (
                        f"Not enough stock for {product.name} "
                        f"in {source_branch.name}"
                    ),
                )

            source_after = source_before - item.quantity
            destination_after = (
                destination_before + item.quantity
            )

            source_balance.quantity = source_after
            destination_balance.quantity = destination_after

            await self.repo.sync_product_total(product)

            products.append(product)
            balances.extend(
                [source_balance, destination_balance]
            )

            notes = self._clean(data.notes)

            movements.extend(
                [
                    InventoryMovement(
                        company_id=data.company_id,
                        shop_id=source_branch.shop_id,
                        branch_id=source_branch.id,
                        product_id=product.id,
                        product_name=product.name,
                        movement_type="transfer_out",
                        quantity=item.quantity,
                        before_qty=source_before,
                        after_qty=source_after,
                        unit_cost=Decimal(
                            product.cost_price or 0
                        ),
                        reference=reference,
                        reason=(
                            f"Transfer to "
                            f"{destination_branch.name}"
                        ),
                        notes=notes,
                    ),
                    InventoryMovement(
                        company_id=data.company_id,
                        shop_id=destination_branch.shop_id,
                        branch_id=destination_branch.id,
                        product_id=product.id,
                        product_name=product.name,
                        movement_type="transfer_in",
                        quantity=item.quantity,
                        before_qty=destination_before,
                        after_qty=destination_after,
                        unit_cost=Decimal(
                            product.cost_price or 0
                        ),
                        reference=reference,
                        reason=(
                            f"Transfer from "
                            f"{source_branch.name}"
                        ),
                        notes=notes,
                    ),
                ]
            )

        return await self.repo.save_transfer(
            products,
            balances,
            movements,
        )

    @staticmethod
    def _clean(value: str | None):
        if value is None:
            return None

        cleaned = value.strip()
        return cleaned or None
