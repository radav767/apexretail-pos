from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.sale import Sale


class DashboardRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_summary(self, company_id):
        now = datetime.now(timezone.utc)
        start_today = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        end_today = start_today + timedelta(days=1)

        sales_result = await self.db.execute(
            select(
                func.coalesce(func.sum(Sale.total_amount), 0),
                func.count(Sale.id),
            ).where(
                Sale.company_id == company_id,
                Sale.status == "completed",
                Sale.created_at >= start_today,
                Sale.created_at < end_today,
            )
        )
        today_sales, today_transactions = sales_result.one()

        products_result = await self.db.execute(
            select(func.count(Product.id)).where(
                Product.company_id == company_id,
                Product.active == True,
                Product.deleted == False,
            )
        )
        total_products = products_result.scalar_one()

        low_stock_result = await self.db.execute(
            select(func.count(Product.id)).where(
                Product.company_id == company_id,
                Product.active == True,
                Product.deleted == False,
                Product.stock_qty <= Product.reorder_level,
            )
        )
        low_stock_products = low_stock_result.scalar_one()

        stock_value_result = await self.db.execute(
            select(
                func.coalesce(
                    func.sum(Product.stock_qty * Product.cost_price),
                    0,
                )
            ).where(
                Product.company_id == company_id,
                Product.active == True,
                Product.deleted == False,
            )
        )
        stock_value = stock_value_result.scalar_one()

        return {
            "today_sales": today_sales,
            "today_transactions": today_transactions,
            "total_products": total_products,
            "low_stock_products": low_stock_products,
            "stock_value": stock_value,
        }
