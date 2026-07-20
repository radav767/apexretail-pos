import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate


class SalesService:
    def __init__(self, repo: SalesRepository):
        self.repo = repo

    async def create_sale(self, data: SaleCreate):
        if not data.items:
            raise HTTPException(400, "Sale must contain at least one item")

        payment_method = data.payment_method.strip().lower()

        if payment_method not in {"cash", "card", "mobile", "credit"}:
            raise HTTPException(400, "Unsupported payment method")

        sale_id = uuid.uuid4()
        receipt_number = (
            f"APR-{datetime.now(timezone.utc):%Y%m%d}-"
            f"{str(sale_id)[:8].upper()}"
        )

        total = Decimal("0")
        sale_items: list[SaleItem] = []
        products_to_update = []

        for item in data.items:
            product = await self.repo.get_product(item.product_id)

            if not product:
                raise HTTPException(404, "Product not found")

            if product.company_id != data.company_id:
                raise HTTPException(
                    403,
                    "Product does not belong to this company",
                )

            if product.stock_qty < item.quantity:
                raise HTTPException(
                    400,
                    f"Not enough stock for {product.name}",
                )

            line_total = product.selling_price * item.quantity
            total += line_total

            product.stock_qty -= item.quantity
            products_to_update.append(product)

            sale_items.append(
                SaleItem(
                    sale_id=sale_id,
                    product_id=product.id,
                    product_name=product.name,
                    quantity=item.quantity,
                    unit_price=product.selling_price,
                    line_total=line_total,
                )
            )

        if payment_method == "cash":
            amount_received = data.amount_received or Decimal("0")

            if amount_received < total:
                raise HTTPException(
                    400,
                    "Amount received is less than the sale total",
                )

            change_due = amount_received - total
        else:
            amount_received = total
            change_due = Decimal("0")

        sale = Sale(
            id=sale_id,
            company_id=data.company_id,
            receipt_number=receipt_number,
            total_amount=total,
            amount_received=amount_received,
            change_due=change_due,
            payment_method=payment_method,
            status="completed",
        )

        return await self.repo.save_sale(
            sale,
            sale_items,
            products_to_update,
        )

    async def list_sales(self, company_id, limit: int = 100):
        return await self.repo.list_sales(company_id, limit)
