from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


SalesHistoryView = Literal[
    "individual", "cashier", "product", "category", "payment_type",
    "shop_branch", "credit_sales", "refunds_cancellations",
]


class SalesHistoryQuery(BaseModel):
    view: SalesHistoryView = "individual"
    date_from: date
    date_to: date
    shop_id: UUID | None = None
    branch_id: UUID | None = None
    cashier_id: UUID | None = None
    product_id: UUID | None = None
    category_id: UUID | None = None
    payment_method: str | None = Field(default=None, max_length=40)
    sort_by: str = Field(default="amount", max_length=40)
    sort_dir: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class AvailabilityMetric(BaseModel):
    available: bool
    value: Decimal | None
    reason: str | None = None
    missing_persistence: str | None = None


class SalesHistoryResponse(BaseModel):
    view: SalesHistoryView
    date_from: date
    date_to: date
    reporting_timezone: str
    currency_symbol: str
    decimal_places: int
    total: int
    limit: int
    offset: int
    summary: dict[str, Any]
    rows: list[dict[str, Any]]
    filters: dict[str, Any]
    options: dict[str, list[dict[str, Any]]]


class InventoryValuationRow(BaseModel):
    product_id: UUID
    product_name: str
    sku: str | None
    branch_id: UUID
    branch_name: str
    shop_id: UUID
    shop_name: str
    quantity: Decimal
    selling_value: AvailabilityMetric
    cost_value: AvailabilityMetric
    projected_gross_profit: AvailabilityMetric
    margin_percentage: AvailabilityMetric


class InventoryValuationResponse(BaseModel):
    as_of: datetime
    basis: str
    currency_symbol: str
    decimal_places: int
    total: int
    limit: int
    offset: int
    summary: dict[str, Any]
    rows: list[InventoryValuationRow]


class FinancialSummaryResponse(BaseModel):
    net_sales: Decimal
    cost_of_sales: Decimal
    gross_profit: Decimal
    operating_expenses: Decimal
    net_profit: Decimal
    cash_sales: Decimal
    cash_settlements: Decimal
    cash_expenses: Decimal
    expected_cash_movement: Decimal
    card_settlements: Decimal
    mobile_settlements: Decimal
    card_expenses: Decimal
    mobile_expenses: Decimal
