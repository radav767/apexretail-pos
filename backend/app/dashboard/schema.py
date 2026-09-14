from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    today_sales: Decimal
    today_transactions: int
    total_products: int
    low_stock_products: int
    stock_value: Decimal


class DashboardMetric(BaseModel):
    available: bool
    value: Decimal | None = None
    reason: str | None = None
    missing_persistence: str | None = None


class DashboardShopOption(BaseModel):
    id: UUID
    name: str


class DashboardPhase2Metrics(BaseModel):
    gross_sales: DashboardMetric
    net_sales: DashboardMetric
    cost_of_sales: DashboardMetric
    gross_profit: DashboardMetric
    discounts: DashboardMetric
    refunds: DashboardMetric


class DashboardPhase2Summary(BaseModel):
    range_key: Literal[
        "today",
        "yesterday",
        "last_7_days",
        "last_month",
        "custom",
    ]
    date_from: date
    date_to: date
    reporting_timezone: str
    shop_id: UUID | None = None
    currency_symbol: str
    decimal_places: int
    shops: list[DashboardShopOption]
    metrics: DashboardPhase2Metrics


class DashboardChange(BaseModel):
    available: bool = True
    amount: Decimal | None = None
    percentage: Decimal | None = None
    reason: str | None = None


class DashboardComparison(BaseModel):
    date_from: date
    date_to: date
    metrics: dict[str, DashboardChange]


class DashboardTrendPoint(BaseModel):
    period_start: date
    period_end: date
    metrics: DashboardPhase2Metrics


class DashboardRankedRow(BaseModel):
    id: UUID | None = None
    name: str
    revenue: Decimal
    quantity: Decimal
    gross_profit: Decimal


class DashboardBreakdownRow(BaseModel):
    key: str
    name: str
    transactions: int
    gross_sales: Decimal
    refunds: Decimal
    net_sales: Decimal
    gross_profit: Decimal
    discounts: DashboardMetric


class DashboardPhase3Summary(DashboardPhase2Summary):
    granularity: Literal["day", "week", "month"]
    comparison: DashboardComparison
    trends: list[DashboardTrendPoint]
    top_products: list[DashboardRankedRow]
    top_categories: list[DashboardRankedRow]
    payment_methods: list[DashboardBreakdownRow]
    shop_breakdown: list[DashboardBreakdownRow]
    cashier_breakdown: list[DashboardBreakdownRow]
    discount_breakdown: list[DashboardBreakdownRow]
    refund_breakdown: list[DashboardBreakdownRow]


class DashboardSaleRow(BaseModel):
    id: UUID
    receipt_number: str
    created_at: datetime
    shop_id: UUID | None = None
    shop_name: str
    cashier_name: str
    payment_method: str
    status: str
    original_sale_id: UUID | None = None
    gross_sales: Decimal
    refunds: Decimal
    net_sales: Decimal
    cost_of_sales: Decimal
    gross_profit: Decimal
    discounts: DashboardMetric


class DashboardDrilldown(BaseModel):
    total: int
    limit: int
    offset: int
    rows: list[DashboardSaleRow]
