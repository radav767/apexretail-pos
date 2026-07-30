import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from app.models.inventory_movement import InventoryMovement
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.sales.repository import SalesRepository
from app.sales.schema import SaleCreate


class SalesService:
    def __init__(self, repo: SalesRepository):
        self.repo = repo

    async def create_sale(self, data: SaleCreate):
        employee = None
        if not data.items:
            raise HTTPException(
                400,
                "Sale must contain at least one item",
            )

        payment_method = data.payment_method.strip().lower()

        if payment_method not in {
            "cash",
            "card",
            "mobile",
            "credit",
        }:
            raise HTTPException(
                400,
                "Unsupported payment method",
            )

        branch = await self.repo.resolve_branch(
            data.company_id,
            data.branch_id,
        )

        sale_id = uuid.uuid4()

        receipt_number = (
            f"APR-{datetime.now(timezone.utc):%Y%m%d}-"
            f"{str(sale_id)[:8].upper()}"
        )

        total = Decimal("0")
        sale_items = []
        products = []
        balances = []
        inventory_movements = []
        seen_products = set()

        for item in data.items:
            if item.product_id in seen_products:
                raise HTTPException(
                    400,
                    "The same product appears more than once",
                )

            seen_products.add(item.product_id)

            product = await self.repo.get_product(
                data.company_id,
                item.product_id,
            )

            balance = await self.repo.get_balance(
                data.company_id,
                branch,
                product,
            )

            before_qty = Decimal(balance.quantity or 0)

            if before_qty < item.quantity:
                raise HTTPException(
                    400,
                    (
                        f"Not enough stock for {product.name} "
                        f"in the selected branch"
                    ),
                )

            after_qty = before_qty - item.quantity

            selling_price = Decimal(
                product.selling_price or 0
            )

            unit_cost = Decimal(product.cost_price or 0)

            line_cost = unit_cost * item.quantity


            line_total = selling_price * item.quantity
            total += line_total

            balance.quantity = after_qty
            await self.repo.sync_product_total(product)

            products.append(product)
            balances.append(balance)

            sale_items.append(
                SaleItem(
                    sale_id=sale_id,
                    product_id=product.id,
                    product_name=product.name,
                    quantity=item.quantity,
                    unit_price=selling_price,
                    line_total=line_total,
                    unit_cost=unit_cost,
                    line_cost=line_cost,
                )
            )

            inventory_movements.append(
                InventoryMovement(
                    company_id=data.company_id,
                    shop_id=branch.shop_id,
                    branch_id=branch.id,
                    product_id=product.id,
                    product_name=product.name,
                    movement_type="sale",
                    quantity=item.quantity,
                    before_qty=before_qty,
                    after_qty=after_qty,
                    unit_cost=Decimal(
                        product.cost_price or 0
                    ),
                    reference=receipt_number,
                    reason="POS sale",
                    notes=(
                        f"Stock deducted by receipt "
                        f"{receipt_number}"
                    ),
                )
            )

        if payment_method == "cash":
            amount_received = (
                data.amount_received
                if data.amount_received is not None
                else Decimal("0")
            )

            if amount_received < total:
                raise HTTPException(
                    400,
                    "Amount received is less than the sale total",
                )

            change_due = amount_received - total
        else:
            amount_received = total
            change_due = Decimal("0")



        if data.employee_id is not None:
            employee = await self.repo.get_employee(
                                 employee_id=data.employee_id,
                                 company_id=data.company_id,
                             )

            if not employee:
                raise HTTPException(
                    400,
                    "Employee not found or inactive",
                )

            if (
                employee.branch_id != branch.id
                and employee.role
                not in {"owner", "manager"}
            ):
                raise HTTPException(
                    400,
                    "Employee is not assigned to this branch",
                )

        sale = Sale(
            id=sale_id,
            company_id=data.company_id,
            shop_id=branch.shop_id,
            branch_id=branch.id,
            employee_id=employee.id if employee else None,
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
            products,
            balances,
            inventory_movements,
        )

    async def list_sales(
        self,
        company_id,
        limit: int = 100,
    ):
        return await self.repo.list_sales(
            company_id,
            limit,
        )
