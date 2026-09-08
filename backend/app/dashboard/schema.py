from datetime import date
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
