from decimal import Decimal
import uuid
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

        total = Decimal("0")
        sale_items = []
        products_to_update = []

        sale = Sale(
            id=uuid.uuid4(),
            company_id=data.company_id,
            payment_method=data.payment_method,
            total_amount=Decimal("0"),
            status="completed",
        )

        for item in data.items:
            product = await self.repo.get_product(item.product_id)

            if not product:
                raise HTTPException(404, "Product not found")

            if product.company_id != data.company_id:
                raise HTTPException(403, "Product does not belong to this company")

            if product.stock_qty < item.quantity:
                raise HTTPException(400, f"Not enough stock for {product.name}")

            line_total = product.selling_price * item.quantity
            total += line_total

            product.stock_qty = product.stock_qty - item.quantity
            products_to_update.append(product)

            sale_items.append(
                SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    product_name=product.name,
                    quantity=item.quantity,
                    unit_price=product.selling_price,
                    line_total=line_total,
                )
            )

        sale.total_amount = total

        return await self.repo.save_sale(sale, sale_items, products_to_update)
