from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException

from app.inventory.branch_repository import (
    BranchInventoryRepository,
)
from app.inventory.branch_schema import BranchCreate


class BranchInventoryService:
    def __init__(
        self,
        repo: BranchInventoryRepository,
    ):
        self.repo = repo

    async def branches(self, company_id: UUID):
        return await self.repo.list_branches(company_id)

    async def create_branch(self, data: BranchCreate, actor=None):
        if hasattr(self.repo,'db'):
            from app.subscriptions.commercial import enforce_capacity
            await enforce_capacity(self.repo.db,data.company_id,'branch')
        name = data.name.strip()

        if not name:
            raise HTTPException(
                400,
                "Branch name is required",
            )

        shop = await self.repo.get_shop(
            data.company_id,
            data.shop_id,
        )

        if not shop:
            raise HTTPException(
                404,
                "Shop not found or inactive",
            )

        duplicate = await self.repo.find_branch_name(
            data.company_id,
            shop.id,
            name,
        )

        if duplicate:
            raise HTTPException(
                409,
                "A branch with this name already exists",
            )

        return await self.repo.create_branch(
            data.company_id,
            shop,
            name,
            actor=actor,
        )

    async def overview(
        self,
        company_id: UUID,
        branch_id: UUID | None,
    ):
        rows = await self.repo.list_balances(
            company_id,
            branch_id,
        )

        response = []

        for row in rows:
            quantity = Decimal(row["quantity"] or 0)
            reorder_level = Decimal(
                row["reorder_level"] or 0
            )
            cost_price = (
                Decimal(row["cost_price"])
                if row["cost_price"] is not None
                else None
            )

            response.append(
                {
                    **row,
                    "quantity": quantity,
                    "reorder_level": reorder_level,
                    "cost_price": cost_price,
                    "stock_value": quantity * cost_price if cost_price is not None else None,
                    "low_stock": quantity <= reorder_level,
                }
            )

        return response
