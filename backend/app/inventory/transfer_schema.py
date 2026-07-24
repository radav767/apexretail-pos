from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class TransferItem(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0)


class TransferCreate(BaseModel):
    company_id: UUID
    source_branch_id: UUID
    destination_branch_id: UUID

    items: list[TransferItem] = Field(min_length=1)

    reference: str | None = Field(
        default=None,
        max_length=80,
    )

    notes: str | None = Field(
        default=None,
        max_length=1000,
    )
