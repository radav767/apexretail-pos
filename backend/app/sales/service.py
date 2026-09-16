from app.business_settings.service import BusinessSettingsService
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException

from app.auth.dependencies import AuthActor
from app.employees.service import EmployeeService
from app.models.inventory_movement import InventoryMovement
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.audit_event import AuditEvent
from app.sales.repository import SalesRepository
from app.sales.schema import RefundCreate, SaleCreate
from app.devices.authority import (
    TERMINAL_ASSIGNMENT_CHANGED,
    TERMINAL_DECOMMISSIONED,
    TERMINAL_IDENTITY_REVOKED,
    terminal_authority_error,
)


VALID_WEIGHT_ENTRY_UNITS = {"kg", "litre"}
VALID_PRODUCT_UNITS = {"each", "kg", "g", "litre", "ml"}


class SalesService:
    def __init__(self, repo: SalesRepository):
        self.repo = repo

    async def create_sale(
        self,
        data: SaleCreate,
        *,
        actor: AuthActor | None,
    ):
        device = None
        employee = None

        if actor is not None:
            if actor.company_id != data.company_id:
                raise HTTPException(403, "Forbidden")

            if actor.actor_type == "employee":
                if (
                    not actor.permissions
                    or actor.permissions.get("sales") is False
                ):
                    raise HTTPException(
                        403,
                        "Permission denied",
                    )

                if (
                    data.discount_amount is not None
                    and data.discount_amount > 0
                    and not actor.permissions.get("discounts")
                ):
                    raise HTTPException(
                        403,
                        "Discount permission denied",
                    )

                data.employee_id = actor.employee.id

        # An Android device may submit the same queued sale more than
        # once when connectivity returns. Return the existing sale
        # instead of deducting stock again.
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

        if data.device_id is not None or data.device_key:
            device = await self.repo.get_device(
                data.company_id,
                device_id=data.device_id,
                device_key=(
                    data.device_key.strip()
                    if data.device_key
                    else None
                ),
            )

            if device is None:
                raise terminal_authority_error(
                    403,
                    TERMINAL_IDENTITY_REVOKED,
                    "Device not found or inactive",
                )

            if hasattr(device, "branch_id") and branch.id != device.branch_id:
                raise terminal_authority_error(
                    409,
                    TERMINAL_ASSIGNMENT_CHANGED,
                    "The terminal assignment changed. Review and resubmit the sale for its current branch.",
                )
            if (
                data.assignment_revision is not None
                and data.assignment_revision != getattr(device, "assignment_revision", 1)
            ):
                raise terminal_authority_error(
                    409,
                    TERMINAL_ASSIGNMENT_CHANGED,
                    "The terminal assignment revision is stale",
                )

            blocked_at = device.removed_at or device.deactivated_at
            if (
                blocked_at is not None
                and (
                    data.client_created_at is None
                    or data.client_created_at > blocked_at
                )
            ):
                raise terminal_authority_error(
                    403,
                    TERMINAL_DECOMMISSIONED,
                    "Device access has been disabled",
                )

        # Idempotent retries remain safe, but only after the current terminal
        # identity and assignment have been authorized.
        existing_client_sale = (
            await self.repo.get_by_client_sale_id(data.company_id, data.client_sale_id)
            if data.client_sale_id
            else None
        )
        if existing_client_sale:
            return existing_client_sale

        sale_id = uuid.uuid4()

        receipt_number = (
            f"APR-{datetime.now(timezone.utc):%Y%m%d}-"
            f"{str(sale_id)[:8].upper()}"
        )

        # Load the tax configuration used for this transaction.

        settings = await BusinessSettingsService(self.repo.db).get(

            data.company_id

        )

        tax_name = str(

            settings.get("tax_name") or "Tax"

        ).strip() or "Tax"

        tax_rate = Decimal(

            str(settings.get("tax_rate") or 0)

        )

        tax_inclusive = bool(

            settings.get("tax_inclusive", False)

        )

        shop = await self.repo.get_shop(
            data.company_id,
            branch.shop_id,
        )
        shop_address_snapshot = None
        if shop is not None:
            address_payload = {
                "address_line_1": shop.address_line_1,
                "address_line_2": shop.address_line_2,
                "city": shop.city,
                "state_province": shop.state_province,
                "country": shop.country,
                "phone": shop.phone,
                "tax_vat_number": shop.tax_vat_number,
            }
            if any(address_payload.values()):
                shop_address_snapshot = address_payload

        money_quantum = Decimal("0.01")


        total = Decimal("0")
        undiscounted_total = Decimal("0")
        sale_items = []
        line_discount_total = Decimal("0.00")
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

            selling_unit = (
                str(
                    item.selling_unit
                    or getattr(product, "unit", None)
                    or "each"
                )
                .strip()
                .lower()
            ) or "each"
            if selling_unit not in VALID_PRODUCT_UNITS:
                raise HTTPException(400, "Unsupported selling unit")
            selling_price = (
                Decimal(item.unit_price)
                if item.unit_price is not None
                else Decimal(product.selling_price or 0)
            )
            if item.quantity <= 0:
                raise HTTPException(400, "Quantity must be greater than zero")
            if selling_price <= 0:
                raise HTTPException(400, "Unit price must be greater than zero")

            cost_snapshot_available = product.cost_price is not None
            unit_cost = (
                Decimal(product.cost_price)
                if cost_snapshot_available
                else Decimal("0")
            )

            line_cost = (
                unit_cost * item.quantity
            ).quantize(
                money_quantum,
                rounding=ROUND_HALF_UP,
            )

            line_total = (
                Decimal(item.line_total)
                if item.line_total is not None
                else selling_price * item.quantity
            ).quantize(
                money_quantum,
                rounding=ROUND_HALF_UP,
            )
            if line_total <= 0:
                raise HTTPException(400, "Line total must be greater than zero")
            if data.discount_amount is not None and line_total > (
                selling_price * item.quantity
            ).quantize(money_quantum, rounding=ROUND_HALF_UP):
                raise HTTPException(400, "Discounted line total exceeds unit-price total")
            line_discount_amount = (
                Decimal(item.line_discount_amount).quantize(
                    money_quantum,
                    rounding=ROUND_HALF_UP,
                )
                if item.line_discount_amount is not None
                else None
            )
            gross_line_total = (selling_price * item.quantity).quantize(
                money_quantum,
                rounding=ROUND_HALF_UP,
            )
            if (
                line_discount_amount is not None
                and line_discount_amount >= gross_line_total
            ):
                raise HTTPException(
                    400,
                    "Line discount must be less than the line amount",
                )
            line_discount_total += line_discount_amount or Decimal("0.00")
            total += line_total
            undiscounted_total += (
                selling_price * item.quantity
            ).quantize(
                money_quantum,
                rounding=ROUND_HALF_UP,
            )

            balance.quantity = after_qty
            await self.repo.sync_product_total(product)

            products.append(product)
            balances.append(balance)

            sale_items.append(
                SaleItem(
                    sale_id=sale_id,
                    product_id=product.id,
                    product_name=product.name,
                    category_id_snapshot=getattr(product, "category_id", None),
                    category_name_snapshot=(
                        await self.repo.get_category_name(
                            data.company_id, getattr(product, "category_id", None)
                        )
                        if getattr(product, "category_id", None) is not None
                        else None
                    ),
                    quantity=item.quantity,
                    selling_unit=selling_unit,
                    unit_price=selling_price,
                    line_total=line_total,
                    line_discount_amount=line_discount_amount,
                    unit_cost=unit_cost,
                    line_cost=line_cost,
                    cost_snapshot_available=cost_snapshot_available,
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

        # Calculate the final tax snapshot.
        raw_item_total = total
        discount_amount = None
        sale_discount_amount = None
        if data.discount_amount is not None:
            discount_amount = Decimal(
                data.discount_amount
            ).quantize(
                money_quantum,
                rounding=ROUND_HALF_UP,
            )
            inferred_discount = (
                undiscounted_total - raw_item_total
            ).quantize(
                money_quantum,
                rounding=ROUND_HALF_UP,
            )
            if inferred_discount < 0 or discount_amount != inferred_discount:
                raise HTTPException(
                    400,
                    (
                        "discount_amount must equal the reduction from "
                        "unit-price totals to submitted line totals"
                    ),
                )
            if data.sale_discount_amount is not None:
                sale_discount_amount = Decimal(
                    data.sale_discount_amount
                ).quantize(
                    money_quantum,
                    rounding=ROUND_HALF_UP,
                )
                if (
                    line_discount_total + sale_discount_amount
                    != discount_amount
                ):
                    raise HTTPException(
                        400,
                        (
                            "discount_amount must equal line discounts plus "
                            "the sale-wide discount"
                        ),
                    )
            elif any(
                item.line_discount_amount is not None
                for item in data.items
            ):
                raise HTTPException(
                    400,
                    "sale_discount_amount is required with explicit line discounts",
                )
        elif (
            data.sale_discount_amount is not None
            or any(item.line_discount_amount is not None for item in data.items)
        ):
            raise HTTPException(
                400,
                "discount_amount is required with discount components",
            )

        if tax_rate > 0:
            tax_fraction = tax_rate / Decimal("100")

            if tax_inclusive:
                total_amount = raw_item_total.quantize(
                    money_quantum,
                    rounding=ROUND_HALF_UP,
                )
                subtotal_amount = (
                    total_amount
                    / (Decimal("1") + tax_fraction)
                ).quantize(
                    money_quantum,
                    rounding=ROUND_HALF_UP,
                )
                tax_amount = (
                    total_amount - subtotal_amount
                ).quantize(
                    money_quantum,
                    rounding=ROUND_HALF_UP,
                )
            else:
                subtotal_amount = raw_item_total.quantize(
                    money_quantum,
                    rounding=ROUND_HALF_UP,
                )
                tax_amount = (
                    subtotal_amount * tax_fraction
                ).quantize(
                    money_quantum,
                    rounding=ROUND_HALF_UP,
                )
                total_amount = (
                    subtotal_amount + tax_amount
                ).quantize(
                    money_quantum,
                    rounding=ROUND_HALF_UP,
                )
        else:
            subtotal_amount = raw_item_total.quantize(
                money_quantum,
                rounding=ROUND_HALF_UP,
            )
            tax_amount = Decimal("0.00")
            total_amount = subtotal_amount

        total = total_amount

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

            permissions = EmployeeService.build_permissions(
                employee.role,
                employee.permissions,
            )

            if permissions.get("sales") is False:
                raise HTTPException(
                    403,
                    "Permission denied",
                )

            if discount_amount and not permissions.get("discounts"):
                raise HTTPException(403, "Discount permission denied")

        if total >= Decimal("10000000000"):
            raise HTTPException(400, "Sale amount exceeds supported limit")

        sale = Sale(
            id=sale_id,
            company_id=data.company_id,
            client_sale_id=data.client_sale_id,
            client_created_at=data.client_created_at,
            created_at=(
                data.client_created_at
                or datetime.now(timezone.utc)
            ),
            shop_id=branch.shop_id,
            branch_id=branch.id,
            device_id=device.id if device else None,
            employee_id=employee.id if employee else None,
            cashier_name=employee.name if employee else None,
            shop_name_snapshot=shop.name if shop else None,
            shop_address_snapshot=shop_address_snapshot,
            branch_name_snapshot=branch.name,
            pos_name_snapshot=(
                (
                    device.friendly_name
                    or device.name
                )
                if device
                else None
            ),
            pos_number_snapshot=(
                str(device.pos_number)
                if device and device.pos_number is not None
                else None
            ),
            receipt_footer_snapshot=settings.get(
                "receipt_footer"
            ),
            receipt_number=receipt_number,
            subtotal_amount=subtotal_amount,
            tax_name=tax_name,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            tax_inclusive=tax_inclusive,
            total_amount=total,
            discount_amount=discount_amount,
            sale_discount_amount=sale_discount_amount,
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

    async def create_refund(
        self,
        data: RefundCreate,
        *,
        actor: AuthActor | None,
    ):
        if actor is not None:
            if actor.company_id != data.company_id:
                raise HTTPException(403, "Forbidden")
            if (
                actor.actor_type == "employee"
                and (
                    not actor.permissions
                    or actor.permissions.get("refunds") is False
                )
            ):
                raise HTTPException(403, "Permission denied")

        original_sale = await self.repo.get_sale_for_update(
            data.company_id,
            data.original_sale_id,
        )
        if original_sale is None:
            raise HTTPException(404, "Original sale not found")

        sale_items = {
            item.id: item
            for item in await self.repo.get_sale_items(
                data.original_sale_id
            )
        }
        if not sale_items:
            raise HTTPException(400, "Original sale has no items")
        if original_sale.original_sale_id is not None or original_sale.status not in {"completed", "partially_refunded"}:
            raise HTTPException(400, "Only completed original sales can be refunded")
        if not data.reason.strip():
            raise HTTPException(400, "Refund reason is required")
        if data.refund_method and data.refund_method != original_sale.payment_method and (actor is None or actor.role not in {"owner", "manager", "administrator"}):
            raise HTTPException(403, "Only a manager may change the refund method")

        branch = await self.repo.resolve_branch(
            data.company_id,
            data.branch_id or original_sale.branch_id,
        )
        refund_id = uuid.uuid4()
        receipt_number = (
            f"RFD-{datetime.now(timezone.utc):%Y%m%d}-"
            f"{str(refund_id)[:8].upper()}"
        )
        money_quantum = Decimal("0.01")
        refund_sale_items = []
        products = []
        balances = []
        inventory_movements = []
        total = Decimal("0.00")

        seen = set()
        for refund_item in data.items:
            if refund_item.sale_item_id in seen:
                raise HTTPException(400, "Each sale item may appear only once")
            seen.add(refund_item.sale_item_id)
            original_item = sale_items.get(refund_item.sale_item_id)
            if original_item is None:
                raise HTTPException(400, "Refund item not found in original sale")
            previous_refunds = await self.repo.list_refund_items_for_original_item(
                refund_item.sale_item_id
            )
            already_refunded = sum(
                (Decimal(item.quantity or 0) for item in previous_refunds),
                Decimal("0"),
            )
            remaining = Decimal(original_item.quantity or 0) - already_refunded
            if refund_item.quantity > remaining:
                raise HTTPException(400, "Refund quantity exceeds remaining quantity")

            product = await self.repo.get_product(
                data.company_id,
                original_item.product_id,
            )
            balance = await self.repo.get_balance(
                data.company_id,
                branch,
                product,
            )
            before_qty = Decimal(balance.quantity or 0)
            after_qty = before_qty + refund_item.quantity
            balance.quantity = after_qty
            await self.repo.sync_product_total(product)

            ratio = refund_item.quantity / Decimal(original_item.quantity or 1)
            line_total = (Decimal(original_item.line_total or 0) * ratio).quantize(
                money_quantum,
                rounding=ROUND_HALF_UP,
            )
            line_cost = (
                Decimal(original_item.unit_cost or 0)
                * refund_item.quantity
            ).quantize(
                money_quantum,
                rounding=ROUND_HALF_UP,
            )
            total += line_total
            products.append(product)
            balances.append(balance)
            refund_sale_items.append(
                SaleItem(
                    sale_id=refund_id,
                    product_id=original_item.product_id,
                    original_sale_item_id=original_item.id,
                    product_name=original_item.product_name,
                    category_id_snapshot=original_item.category_id_snapshot,
                    category_name_snapshot=original_item.category_name_snapshot,
                    quantity=refund_item.quantity,
                    selling_unit=original_item.selling_unit,
                    unit_price=original_item.unit_price,
                    line_total=-line_total,
                    unit_cost=original_item.unit_cost,
                    line_cost=-line_cost,
                    cost_snapshot_available=(
                        original_item.cost_snapshot_available is True
                    ),
                )
            )
            inventory_movements.append(
                InventoryMovement(
                    company_id=data.company_id,
                    shop_id=branch.shop_id,
                    branch_id=branch.id,
                    product_id=product.id,
                    product_name=product.name,
                    movement_type="refund",
                    quantity=refund_item.quantity,
                    before_qty=before_qty,
                    after_qty=after_qty,
                    unit_cost=Decimal(product.cost_price or 0),
                    reference=receipt_number,
                    reason=data.reason.strip(),
                    notes=f"Inventory restored by refund {receipt_number}",
                )
            )

        refund_sale = Sale(
            id=refund_id,
            company_id=data.company_id,
            original_sale_id=original_sale.id,
            shop_id=original_sale.shop_id,
            branch_id=branch.id,
            device_id=data.device_id or original_sale.device_id,
            employee_id=data.employee_id or original_sale.employee_id,
            cashier_name=original_sale.cashier_name,
            shop_name_snapshot=original_sale.shop_name_snapshot,
            shop_address_snapshot=original_sale.shop_address_snapshot,
            branch_name_snapshot=original_sale.branch_name_snapshot,
            pos_name_snapshot=original_sale.pos_name_snapshot,
            pos_number_snapshot=original_sale.pos_number_snapshot,
            receipt_footer_snapshot=original_sale.receipt_footer_snapshot,
            receipt_number=receipt_number,
            subtotal_amount=-total,
            tax_name=original_sale.tax_name,
            tax_rate=original_sale.tax_rate,
            tax_amount=-(Decimal(original_sale.tax_amount or 0) * (total / Decimal(original_sale.subtotal_amount or 1))).quantize(money_quantum, rounding=ROUND_HALF_UP),
            tax_inclusive=original_sale.tax_inclusive,
            total_amount=-(total + (Decimal(original_sale.tax_amount or 0) * (total / Decimal(original_sale.subtotal_amount or 1))).quantize(money_quantum, rounding=ROUND_HALF_UP)),
            amount_received=Decimal("0.00"),
            change_due=Decimal("0.00"),
            payment_method=data.refund_method or original_sale.payment_method,
            status="refunded",
            refund_reason=data.reason.strip(),
            refund_method=data.refund_method or original_sale.payment_method,
            created_at=datetime.now(timezone.utc),
        )
        requested = {i.sale_item_id: i.quantity for i in data.items}
        original_sale.status = "refunded" if all([
            requested.get(item.id, Decimal("0")) + sum((Decimal(x.quantity or 0) for x in await self.repo.list_refund_items_for_original_item(item.id)), Decimal("0")) >= Decimal(item.quantity or 0)
            for item in sale_items.values()
        ]) else "partially_refunded"
        self.repo.db.add(AuditEvent(company_id=data.company_id, actor_employee_id=actor.employee.id if actor and actor.actor_type == "employee" else None, actor_user_id=actor.user.id if actor and actor.actor_type == "user" else None, device_id=data.device_id or original_sale.device_id, action="refund", reason=data.reason.strip(), details={"original_sale_id": str(original_sale.id), "refund_sale_id": str(refund_id)}))
        return await self.repo.save_sale(
            refund_sale,
            refund_sale_items,
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

    async def get_sale_receipt(
        self,
        company_id,
        sale_id,
        *,
        actor: AuthActor | None,
        mark_reprint: bool = True,
    ):
        if actor is not None:
            if actor.company_id != company_id:
                raise HTTPException(403, "Forbidden")

            if actor.actor_type == "employee":
                permissions = actor.permissions or {}
                has_sales_permission = bool(permissions.get("sales"))
                has_refunds_permission = bool(permissions.get("refunds"))
                if (
                    (mark_reprint and not has_sales_permission)
                    or (
                        not mark_reprint
                        and not (
                            has_sales_permission
                            or has_refunds_permission
                        )
                    )
                ):
                    raise HTTPException(403, "Permission denied")

        sale_with_items = await self.repo.get_sale_receipt(
            company_id,
            sale_id,
        )

        if sale_with_items is None:
            raise HTTPException(404, "Sale not found")

        sale, items = sale_with_items

        receipt_items = []
        for item in items:
            refunded_quantity = Decimal("0")
            refundable_quantity = Decimal("0")
            if sale.original_sale_id is None:
                refunded_quantity = sum(
                    (
                        Decimal(refund_item.quantity or 0)
                        for refund_item in await self.repo.list_refund_items_for_original_item(item.id)
                    ),
                    Decimal("0"),
                )
                refundable_quantity = max(
                    Decimal(item.quantity or 0) - refunded_quantity,
                    Decimal("0"),
                )
            receipt_items.append(
                {
                    **item.__dict__,
                    "refunded_quantity": refunded_quantity,
                    "refundable_quantity": refundable_quantity,
                }
            )

        if mark_reprint:
            sale.reprint_count = int(sale.reprint_count or 0) + 1
            sale.last_reprinted_at = datetime.now(timezone.utc)
            if hasattr(self.repo.db, "add"):
                self.repo.db.add(AuditEvent(company_id=company_id, actor_employee_id=actor.employee.id if actor and actor.actor_type == "employee" else None, actor_user_id=actor.user.id if actor and actor.actor_type == "user" else None, device_id=getattr(actor.employee, "device_id", None) if actor and actor.actor_type == "employee" else None, action="receipt_reprint", details={"sale_id": str(sale_id), "reprint_count": sale.reprint_count}))
                if hasattr(self.repo.db, "commit"):
                    await self.repo.db.commit()

        return {
            **sale.__dict__,
            "items": receipt_items,
        }
