from decimal import Decimal

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    today_sales: Decimal
    today_transactions: int
    total_products: int
    low_stock_products: int
    stock_value: Decimal
