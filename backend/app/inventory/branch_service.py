from decimal import Decimal
from uuid import UUID

from app.inventory.branch_repository import (
    BranchInventoryRepository,
)


class BranchInventoryService:
    def __init__(
        self,
        repo: BranchInventoryRepository,
    ):
        self.repo = repo

    async def branches(self, company_id: UUID):
        return await self.repo.list_branches(company_id)

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
            cost_price = Decimal(row["cost_price"] or 0)

            response.append(
                {
                    **row,
                    "quantity": quantity,
                    "reorder_level": reorder_level,
                    "cost_price": cost_price,
                    "stock_value": quantity * cost_price,
                    "low_stock": quantity <= reorder_level,
                }
            )

        return response
