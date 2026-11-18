from app.business_settings.service import BusinessSettingsService
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException

from app.auth.dependencies import AuthActor
from app.employees.service import EmployeeService
from app.employees.manager_approval import consume_manager_authorization
from app.employees.permissions import has_permission
from app.financial_access import enforce_actor_branch
from app.models.inventory_movement import InventoryMovement
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_item_component import SaleItemComponent
from app.models.audit_event import AuditEvent
from app.models.credit_receivable import CreditReceivable
from zoneinfo import ZoneInfo
from app.sales.repository import SalesRepository
from app.sales.schema import RefundCreate, SaleCreate
from app.devices.authority import (
    TERMINAL_ASSIGNMENT_CHANGED,
    TERMINAL_DECOMMISSIONED,
    TERMINAL_IDENTITY_REVOKED,
    terminal_authority_error,
)
from app.currencies.repository import CurrencyRepository
from app.currencies.service import CurrencyService, quantize_currency
from app.financial_context import resolve_shift_for_write


VALID_WEIGHT_ENTRY_UNITS = {"kg", "litre"}
VALID_PRODUCT_UNITS = {"each", "kg", "g", "litre", "ml"}


class SalesService:
    def __init__(self, repo: SalesRepository):
        self.repo = repo

    async def by_client_sale_id(self, company_id, client_sale_id, actor):
        if actor is None:
            raise HTTPException(401, "Authentication is required")
        if actor.company_id != company_id:
            raise HTTPException(403, "Forbidden")
        if (
            actor.actor_type == "employee"
            and (
                not actor.permissions
                or actor.permissions.get("sales") is False
            )
        ):
            raise HTTPException(403, "Permission denied")
        sale = await self.repo.get_by_client_sale_id(
            company_id,
            client_sale_id,
        )
        if sale is None:
            raise HTTPException(404, "Sale transaction was not found")
        enforce_actor_branch(actor, sale.branch_id)
        return sale

    @staticmethod
    def validate_currency_quote(data: SaleCreate, snapshot, current_version: int | None):
        if (
            data.currency_config_version is not None
            and current_version is not None
            and current_version != data.currency_config_version
        ):
            raise HTTPException(409, "Payment currency configuration changed. Refresh the quote and try again.")
        if (
            data.exchange_rate_id is not None
            and data.exchange_rate_id != snapshot["exchange_rate_id"]
        ):
            raise HTTPException(409, "Exchange rate changed. Refresh the payment quote and try again.")

    async def currency_from_base(self, company_id, payment_method, currency_code, amount, *, at):
        if hasattr(self.repo.db, "execute"):
            return await CurrencyService(CurrencyRepository(self.repo.db)).resolve_from_base(
                company_id, payment_method, currency_code, amount, at=at,
            )
        # Test and adapter repositories must name their base currency explicitly;
        # never infer an accounting currency when no authoritative DB is present.
        currency = getattr(self.repo, "base_currency", None)
        if currency is None or not getattr(currency, "code", None):
            raise HTTPException(409, "Company base currency configuration is required")
        code = str(currency.code).strip().upper()
        if currency_code and str(currency_code).strip().upper() != code:
            raise HTTPException(409, "Currency validation requires configured company currencies")
        decimal_places = int(getattr(currency, "decimal_places", 2))
        value = quantize_currency(Decimal(amount), decimal_places)
        return {
            "base_currency": currency, "currency": currency,
            "exchange_rate_id": None, "exchange_rate_snapshot": Decimal("1"),
            "original_amount": value, "base_amount": value,
        }

    async def create_sale(
        self,
        data: SaleCreate,
        *,
        actor: AuthActor | None,
        resolved_shift=None,
        resolved_employee=None,
        resolved_device=None,
        resolution_record=None,
        resolution_command_receipt=None,
    ):
        data = data.model_copy(deep=True)
        command_data = data.model_copy(deep=True)
        command_proof = None
        device = resolved_device
        discount_approved = False
        requires_discount_approval = False
        price_override_approved = False
        employee = resolved_employee
        customer = None

        if actor is not None:
            if actor.company_id != data.company_id:
                raise HTTPException(403, "Forbidden")

            if actor.actor_type == "employee":
                if (
                    not actor.permissions
                    or not has_permission(actor.permissions, "sales_process")
                ):
                    raise HTTPException(
                        403,
                        "Permission denied",
                    )

                if (
                    data.discount_amount is not None
                    and data.discount_amount > 0
                    and not has_permission(actor.permissions, "sales_discount")
                ):
                    requires_discount_approval = True

                if actor.employee is not None:
                    data.employee_id = actor.employee.id

        # A malformed employee actor cannot obtain or consume a manager
        # authorization. Preserve the authorization failure before payload
        # validation without touching a repository.
        if requires_discount_approval and (actor is None or actor.employee is None):
            raise HTTPException(403, "Manager approval required")

        if hasattr(self.repo, 'begin_command'):
            if actor is not None and actor.actor_type == 'employee':
                command_data.employee_id = actor.employee.id if actor.employee else None
            committed, command_proof = await self.repo.begin_command(command_data, actor)
            if committed is not None:
                return committed

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
        if actor is not None:
            enforce_actor_branch(actor, branch.id)
        shift = resolved_shift
        if shift is None:
            shift = await resolve_shift_for_write(
                self.repo.db, actor, data.company_id, branch.id, data.shift_id,
                occurred_at=data.client_created_at,
                attach_active=True,
                offline_shift_token=data.offline_shift_token,
            )
        if shift is not None:
            if data.device_id is not None and data.device_id != shift.device_id:
                raise HTTPException(403, "POS device does not match the active shift register")
            data.device_id = shift.device_id
            data.employee_id = shift.employee_id

        if payment_method == "credit" and data.customer_id is None:
            raise HTTPException(400, "A customer is required for a credit sale")
        if data.customer_id is not None:
            if data.client_created_at is not None:
                raise HTTPException(409, "Customer-specific pricing is online-only")
            if actor is None:
                raise HTTPException(401, "Authentication is required for a credit sale")
            if payment_method=="credit" and actor.actor_type == "employee" and not (actor.permissions or {}).get("credit_sales"):
                raise HTTPException(403, "Credit sales permission denied")
            customer = await self.repo.get_customer_for_update(data.company_id, data.customer_id)
            if customer is None:
                raise HTTPException(404, "Customer not found or inactive")
            if payment_method=="credit" and not customer.credit_enabled:
                raise HTTPException(409, "Credit is not enabled for this customer")

        if resolved_device is None and (data.device_id is not None or data.device_key):
            device = await self.repo.get_device(
                data.company_id,
                device_id=data.device_id,
                device_key=(
                    data.device_key.strip()
                    if data.device_key
                    else None
                ),
            )

            if device is None or not getattr(device, 'active', True):
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
        if existing_client_sale and command_proof is None:
            return existing_client_sale

        # Consume approval only after the idempotency lookup. If the first
        # response was lost after commit, a retry must return the committed
        # sale rather than reject its correctly single-use approval token.
        if requires_discount_approval:
            await consume_manager_authorization(
                self.repo.db, actor, data.discount_authorization_token,
                "large_discount", {
                    "client_sale_id": str(data.client_sale_id or ""),
                    "discount_amount": str(data.discount_amount),
                },
            )
            discount_approved = True

        sale_id = uuid.uuid4()

        receipt_number = (
            f"APR-{datetime.now(timezone.utc):%Y%m%d}-"
            f"{str(sale_id)[:8].upper()}"
        )

        # Load the tax configuration used for this transaction.

        settings_service = BusinessSettingsService(self.repo.db)
        settings = (await settings_service.get(data.company_id, commit=False) if command_proof is not None
                    else await settings_service.get(data.company_id))

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
        sale_item_components = []
        seen_products = set()
        product_tax_total=Decimal("0"); has_product_tax_rules=False

        for item in data.items:
            identity=(item.product_id,item.variant_id)
            if identity in seen_products:
                raise HTTPException(
                    400,
                    "The same product appears more than once",
                )

            seen_products.add(identity)

            product = await self.repo.get_product(
                data.company_id,
                item.product_id,
            )
            if hasattr(self.repo, "validate_new_sale_product"):
                await self.repo.validate_new_sale_product(data.company_id, product.id)
            variant=await self.repo.get_variant(data.company_id,product.id,item.variant_id) if item.variant_id and hasattr(self.repo,"get_variant") else None
            if item.variant_id and variant is None: raise HTTPException(400,"Variant is missing or inactive")
            if not item.variant_id and hasattr(self.repo, "has_active_variants") and await self.repo.has_active_variants(data.company_id, product.id):
                raise HTTPException(409, "Select the product variant before completing this sale. Retain previously queued sales for authorized review; never assign a variant silently")

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
            base_price=Decimal(variant.selling_price if variant is not None and variant.selling_price is not None else product.selling_price or 0)
            level_name=str(getattr(customer,"price_level_name","") or "").strip()
            if (
                item.unit_price is not None
                and Decimal(item.unit_price) != base_price
                and level_name == ""
                and actor is not None
                and actor.actor_type == "employee"
                and not has_permission(actor.permissions, "sales_price_override")
                and not price_override_approved
            ):
                await consume_manager_authorization(
                    self.repo.db, actor, data.price_override_authorization_token,
                    "price_override", {"client_sale_id": str(data.client_sale_id or "")},
                )
                price_override_approved = True
            level=await self.repo.get_price_level(data.company_id,product.id,level_name,item.quantity) if level_name and hasattr(self.repo,"get_price_level") else None
            selling_price = Decimal(level.price) if level is not None else (
                Decimal(item.unit_price)
                if item.unit_price is not None
                else base_price
            )
            if item.quantity <= 0:
                raise HTTPException(400, "Quantity must be greater than zero")
            if selling_price <= 0:
                raise HTTPException(400, "Unit price must be greater than zero")

            product_type = str(getattr(product, "product_type", "standard") or "standard")
            track_inventory = bool(getattr(product, "track_inventory", True))
            recipe_rows = []
            if product_type in {"composite", "bundle"}:
                recipe_rows = await self.repo.get_product_components(
                    data.company_id,
                    product.id,
                )
                if not recipe_rows:
                    raise HTTPException(400, f"{product.name} has no active components")

            if recipe_rows:
                cost_snapshot_available = all(
                    component_product.cost_price is not None
                    for _, component_product in recipe_rows
                )
                unit_cost = sum(
                    (
                        Decimal(component.quantity)
                        * Decimal(component_product.cost_price or 0)
                        for component, component_product in recipe_rows
                    ),
                    Decimal("0"),
                )
            else:
                effective_cost=variant.cost_price if variant is not None and variant.cost_price is not None else product.cost_price
                cost_snapshot_available = effective_cost is not None
                unit_cost = (
                    Decimal(effective_cost)
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
                selling_price * item.quantity
                if level is not None
                else Decimal(item.line_total)
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
            explicit=getattr(product,"tax_rate",None) is not None or bool(getattr(product,"tax_exempt",False)); has_product_tax_rules|=explicit
            effective_rate=Decimal("0") if getattr(product,"tax_exempt",False) else Decimal(getattr(product,"tax_rate",None) if getattr(product,"tax_rate",None) is not None else tax_rate)
            fraction=effective_rate/Decimal("100")
            item_tax=((line_total-line_total/(1+fraction)) if tax_inclusive and effective_rate>0 else (line_total*fraction)).quantize(money_quantum,rounding=ROUND_HALF_UP)
            product_tax_total+=item_tax

            sale_item_id = uuid.uuid4()
            sale_items.append(
                SaleItem(
                    id=sale_item_id,
                    sale_id=sale_id,
                    product_id=product.id,
                    variant_id=variant.id if variant else None,
                    variant_name_snapshot=variant.name if variant else None,
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
                    tax_rate_snapshot=effective_rate,tax_amount=item_tax,tax_exempt_snapshot=bool(getattr(product,"tax_exempt",False)),price_level_name_snapshot=level.name if level else None,
                )
            )

            stock_requirements = []
            if recipe_rows:
                for component, component_product in recipe_rows:
                    required_quantity = (
                        Decimal(component.quantity) * Decimal(item.quantity)
                    ).quantize(Decimal("0.001"))
                    stock_requirements.append(
                        (component_product, required_quantity, component.unit)
                    )
                    sale_item_components.append(
                        SaleItemComponent(
                            company_id=data.company_id,
                            sale_item_id=sale_item_id,
                            component_product_id=component_product.id,
                            component_name=component_product.name,
                            quantity=required_quantity,
                            unit=component.unit,
                            unit_cost=Decimal(component_product.cost_price or 0),
                        )
                    )
            elif track_inventory:
                stock_requirements.append((product, Decimal(item.quantity), selling_unit,variant))

            for requirement in stock_requirements:
                stock_product,required_quantity,requirement_unit=requirement[:3]; stock_variant=requirement[3] if len(requirement)>3 else None
                locked_product = await self.repo.get_product(
                    data.company_id,
                    stock_product.id,
                )
                balance = await self.repo.get_variant_balance(data.company_id,branch,locked_product.id,stock_variant.id) if stock_variant else await self.repo.get_balance(
                    data.company_id,
                    branch,
                    locked_product,
                )
                before_qty = Decimal(balance.quantity or 0)
                if before_qty < required_quantity:
                    raise HTTPException(
                        400,
                        f"Not enough stock for {locked_product.name} in the selected branch",
                    )
                after_qty = before_qty - required_quantity
                balance.quantity = after_qty
                if not stock_variant: await self.repo.sync_product_total(locked_product)
                products.append(locked_product)
                balances.append(balance)
                inventory_movements.append(
                    InventoryMovement(
                        company_id=data.company_id,
                        shop_id=branch.shop_id,
                        branch_id=branch.id,
                        product_id=locked_product.id,
                        variant_id=stock_variant.id if stock_variant else None,
                        product_name=f"{locked_product.name} — {stock_variant.name}" if stock_variant else locked_product.name,
                        movement_type="composite_sale" if recipe_rows else "variant_sale" if stock_variant else "sale",
                        quantity=required_quantity,
                        before_qty=before_qty,
                        after_qty=after_qty,
                        unit_cost=Decimal(locked_product.cost_price or 0),
                        reference=receipt_number,
                        reason="POS sale",
                        notes=(
                            f"Component for {product.name}; receipt {receipt_number}"
                            if recipe_rows
                            else f"Stock deducted by receipt {receipt_number}"
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

        if has_product_tax_rules:
            tax_amount=product_tax_total.quantize(money_quantum,rounding=ROUND_HALF_UP)
            if tax_inclusive: total_amount=raw_item_total.quantize(money_quantum); subtotal_amount=total_amount-tax_amount
            else: subtotal_amount=raw_item_total.quantize(money_quantum); total_amount=subtotal_amount+tax_amount
        elif tax_rate > 0:
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

        currency_snapshot = await self.currency_from_base(
            data.company_id, payment_method,
            None if payment_method == "credit" else data.payment_currency_code, total,
            at=data.client_created_at or datetime.now(timezone.utc),
        )
        current_version = None
        if hasattr(self.repo.db, "execute") and data.currency_config_version is not None:
            current_settings = await CurrencyRepository(self.repo.db).settings(
                data.company_id, for_update=True,
            )
            current_version = int(getattr(current_settings, "currency_config_version", 0) or 0)
        self.validate_currency_quote(data, currency_snapshot, current_version)
        base_currency = currency_snapshot["base_currency"]
        payment_currency = currency_snapshot["currency"]
        rate_snapshot = Decimal(currency_snapshot["exchange_rate_snapshot"])
        payment_amount_original = (
            Decimal("0") if payment_method == "credit"
            else Decimal(currency_snapshot["original_amount"])
        )
        tendered_amount_original = payment_amount_original
        change_amount_original = Decimal("0")

        if payment_method == "cash":
            if payment_currency.is_base and data.tendered_amount_original is None:
                tendered_amount_original = quantize_currency(
                    data.amount_received or Decimal("0"), payment_currency.decimal_places
                )
            else:
                if data.tendered_amount_original is None:
                    raise HTTPException(400, "Tendered amount is required for the selected payment currency")
                tendered_amount_original = quantize_currency(
                    data.tendered_amount_original, payment_currency.decimal_places
                )
            if tendered_amount_original < payment_amount_original:
                raise HTTPException(
                    400,
                    "Amount received is less than the sale total",
                )
            change_amount_original = quantize_currency(
                tendered_amount_original - payment_amount_original,
                payment_currency.decimal_places,
            )
            amount_received = quantize_currency(
                tendered_amount_original / rate_snapshot, base_currency.decimal_places
            )
            change_due = quantize_currency(
                change_amount_original / rate_snapshot, base_currency.decimal_places
            )
        elif payment_method == "credit":
            amount_received = Decimal("0.00")
            change_due = Decimal("0.00")
        else:
            amount_received = total
            change_due = Decimal("0")

        if payment_method == "credit" and customer is not None and not customer.unlimited_credit:
            if customer.credit_limit is None:
                raise HTTPException(409, "Customer credit policy has no monetary limit")
            current_outstanding = Decimal(await self.repo.customer_outstanding(data.company_id, customer.id))
            if current_outstanding + total > Decimal(customer.credit_limit):
                raise HTTPException(409, "Credit limit exceeded")



        if resolved_employee is None and data.employee_id is not None:
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

            permissions = await EmployeeService.effective_permissions(employee, self.repo.db)

            if permissions.get("sales") is False:
                raise HTTPException(
                    403,
                    "Permission denied",
                )

            if discount_amount and not has_permission(permissions, "sales_discount") and not discount_approved:
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
            customer_id=customer.id if customer else None,
            customer_name_snapshot=customer.name if customer else None,
            customer_code_snapshot=customer.customer_code if customer else None,
            price_level_name_snapshot=getattr(customer,"price_level_name",None) if customer else None,
            shift_id=shift.id if shift else None,
            base_currency_code=base_currency.code,
            payment_currency_code=base_currency.code if payment_method == "credit" else payment_currency.code,
            exchange_rate_id=None if payment_method == "credit" else currency_snapshot["exchange_rate_id"],
            exchange_rate_snapshot=Decimal("1") if payment_method == "credit" else rate_snapshot,
            payment_amount_original=payment_amount_original,
            tendered_amount_original=tendered_amount_original,
            change_amount_original=change_amount_original,
            cashier_name=employee.name if employee else None,
            shop_name_snapshot=shift.shop_name_snapshot if resolved_shift is not None else (shop.name if shop else None),
            shop_address_snapshot=shop_address_snapshot,
            branch_name_snapshot=shift.branch_name_snapshot if resolved_shift is not None else branch.name,
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

        if discount_amount and hasattr(self.repo.db, "add"):
            self.repo.db.add(AuditEvent(
                company_id=data.company_id,
                actor_employee_id=actor.employee.id if actor and actor.actor_type == "employee" else None,
                actor_user_id=actor.user.id if actor and actor.actor_type == "user" else None,
                device_id=device.id if device else None,
                action="sale_discount_applied",
                details={"sale_id": str(sale.id), "amount": str(discount_amount)},
            ))
        if price_override_approved and hasattr(self.repo.db, "add"):
            self.repo.db.add(AuditEvent(
                company_id=data.company_id,
                actor_employee_id=actor.employee.id if actor and actor.actor_type == "employee" else None,
                actor_user_id=actor.user.id if actor and actor.actor_type == "user" else None,
                device_id=device.id if device else None,
                action="sale_price_override",
                details={"sale_id": str(sale.id)},
            ))

        if resolution_record is not None:
            # The evidence FK targets the new sale. Flush that immutable target
            # first, then let the repository commit sale, stock and audit data
            # atomically in the same transaction.
            self.repo.db.add(sale)
            await self.repo.db.flush([sale])
            resolution_record.sale_id = sale.id
            self.repo.db.add_all([resolution_record, AuditEvent(
                company_id=data.company_id,
                actor_user_id=actor.user.id if actor and actor.actor_type == "user" and actor.user else None,
                actor_employee_id=actor.employee.id if actor and actor.actor_type == "employee" and actor.employee else None,
                device_id=shift.device_id,
                action="offline_sale_posted_to_original_shift",
                reason=resolution_record.reason,
                details={
                    "resolution_id": str(resolution_record.id),
                    "sale_id": str(sale.id),
                    "client_sale_id": str(data.client_sale_id),
                    "original_shift_id": str(shift.id),
                    "payload_sha256": resolution_record.payload_sha256,
                },
            )])

            if resolution_command_receipt is not None:
                self.repo.db.add(resolution_command_receipt)

        if payment_method == "credit" and customer is not None:
            receivable_id = uuid.uuid4()
            receivable = CreditReceivable(
                id=receivable_id,
                company_id=data.company_id,
                sale_id=sale.id,
                customer_id=customer.id,
                shop_id=branch.shop_id,
                branch_id=branch.id,
                cashier_employee_id=employee.id if employee else None,
                device_id=device.id if device else None,
                shift_id=shift.id if shift else None,
                currency_code=await self.repo.get_currency_code(data.company_id),
                original_amount=total,
                amount_settled=Decimal("0.00"),
                outstanding_balance=total,
                due_date=datetime.now(ZoneInfo("Africa/Harare")).date() + timedelta(days=customer.credit_terms_days),
                status="unpaid",
            )
            audit = AuditEvent(
                company_id=data.company_id,
                actor_employee_id=actor.employee.id if actor.actor_type == "employee" else None,
                actor_user_id=actor.user.id if actor.actor_type == "user" else None,
                device_id=device.id if device else None,
                action="credit_sale_created",
                details={"sale_id": str(sale.id), "customer_id": str(customer.id), "receivable_id": str(receivable_id), "amount": str(total)},
            )
            if command_proof is not None:
                self.repo.record_command(command_data, command_proof, sale, device)
            if sale_item_components:
                return await self.repo.save_credit_sale(
                    sale, sale_items, products, balances, inventory_movements,
                    receivable, audit, sale_item_components,
                )
            return await self.repo.save_credit_sale(
                sale, sale_items, products, balances, inventory_movements,
                receivable, audit,
            )

        if command_proof is not None:
            self.repo.record_command(command_data, command_proof, sale, device)
        if sale_item_components:
            return await self.repo.save_sale(
                sale, sale_items, products, balances, inventory_movements,
                sale_item_components,
            )
        return await self.repo.save_sale(
            sale, sale_items, products, balances, inventory_movements,
        )

    async def create_refund(
        self,
        data: RefundCreate,
        *,
        actor: AuthActor | None,
    ):
        if hasattr(self.repo, "begin_command"):
            from app.sales.commands import actor_identity
            from app.subscriptions.write_policy import require_new_write
            actor_identity(actor, data.company_id)
            await require_new_write(self.repo.db, data.company_id)
        if actor is not None:
            if actor.company_id != data.company_id:
                raise HTTPException(403, "Forbidden")
            if (
                actor.actor_type == "employee"
                and (
                    not actor.permissions
                    or not has_permission(actor.permissions, "sales_refund")
                )
            ):
                await consume_manager_authorization(
                    self.repo.db, actor, data.manager_authorization_token,
                    "refund", {"original_sale_id": str(data.original_sale_id)},
                )

        original_sale = await self.repo.get_sale_for_update(
            data.company_id,
            data.original_sale_id,
        )
        if original_sale is None:
            raise HTTPException(404, "Original sale not found")

        if actor is not None:
            enforce_actor_branch(actor, original_sale.branch_id)
            enforce_actor_branch(actor, data.branch_id or original_sale.branch_id)

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
        shift = await resolve_shift_for_write(
            self.repo.db,
            actor,
            data.company_id,
            getattr(branch, "id", data.branch_id or original_sale.branch_id),
            data.shift_id,
            attach_active=True,
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
        refund_tax = Decimal("0.00")

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
            item_tax = (
                Decimal(getattr(original_item, "tax_amount", 0) or 0) * ratio
            ).quantize(money_quantum, rounding=ROUND_HALF_UP)
            refund_tax += item_tax
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
                    variant_id=getattr(original_item, "variant_id", None),
                    variant_name_snapshot=getattr(
                        original_item, "variant_name_snapshot", None
                    ),
                    tax_rate_snapshot=getattr(
                        original_item, "tax_rate_snapshot", None
                    ),
                    tax_amount=-item_tax,
                    tax_exempt_snapshot=bool(
                        getattr(original_item, "tax_exempt_snapshot", False)
                    ),
                    price_level_name_snapshot=getattr(
                        original_item, "price_level_name_snapshot", None
                    ),
                    cost_snapshot_available=(
                        original_item.cost_snapshot_available is True
                    ),
                )
            )

            component_snapshots = (
                await self.repo.get_sale_item_components(
                    data.company_id,
                    original_item.id,
                )
                if hasattr(self.repo, "get_sale_item_components")
                else []
            )
            restore_requirements = []
            if component_snapshots:
                restore_requirements = [
                    (
                        snapshot.component_product_id,
                        snapshot.component_name,
                        (Decimal(snapshot.quantity) * ratio).quantize(Decimal("0.001")),
                        Decimal(snapshot.unit_cost or 0),
                        True,
                    )
                    for snapshot in component_snapshots
                ]
            elif bool(getattr(product, "track_inventory", True)):
                original_variant = None
                if getattr(original_item, "variant_id", None):
                    original_variant = await self.repo.get_variant(
                        data.company_id,
                        original_item.product_id,
                        original_item.variant_id,
                    )
                    if original_variant is None:
                        raise HTTPException(
                            409,
                            "The sold product variant is no longer available for refund",
                        )
                restore_requirements = [
                    (
                        product.id,
                        (
                            f"{product.name} — {original_item.variant_name_snapshot}"
                            if original_variant
                            else product.name
                        ),
                        Decimal(refund_item.quantity),
                        Decimal(original_item.unit_cost or product.cost_price or 0),
                        False,
                        original_variant,
                    )
                ]

            for requirement in restore_requirements:
                restore_product_id, restore_name, restore_quantity, restore_cost, is_component = requirement[:5]
                restore_variant = requirement[5] if len(requirement) > 5 else None
                restore_product = await self.repo.get_product(
                    data.company_id,
                    restore_product_id,
                )
                balance = (
                    await self.repo.get_variant_balance(
                        data.company_id,
                        branch,
                        restore_product.id,
                        restore_variant.id,
                    )
                    if restore_variant
                    else await self.repo.get_balance(
                        data.company_id,
                        branch,
                        restore_product,
                    )
                )
                before_qty = Decimal(balance.quantity or 0)
                after_qty = before_qty + restore_quantity
                balance.quantity = after_qty
                if not restore_variant:
                    await self.repo.sync_product_total(restore_product)
                products.append(restore_product)
                balances.append(balance)
                inventory_movements.append(
                    InventoryMovement(
                        company_id=data.company_id,
                        shop_id=branch.shop_id,
                        branch_id=branch.id,
                        product_id=restore_product.id,
                        variant_id=restore_variant.id if restore_variant else None,
                        product_name=restore_name,
                        movement_type=(
                            "composite_refund"
                            if is_component
                            else "variant_refund"
                            if restore_variant
                            else "refund"
                        ),
                        quantity=restore_quantity,
                        before_qty=before_qty,
                        after_qty=after_qty,
                        unit_cost=restore_cost,
                        reference=receipt_number,
                        reason=data.reason.strip(),
                        notes=f"Inventory restored by refund {receipt_number}",
                    )
                )

        # New sales carry per-line tax snapshots, including tax-exempt lines.
        # Legacy rows predate those columns, so retain the historical aggregate
        # proportional calculation only when no item-level tax is available.
        if not any(getattr(item, "tax_amount", None) is not None for item in sale_items.values()):
            refund_tax = (
                Decimal(original_sale.tax_amount or 0)
                * (total / Decimal(original_sale.subtotal_amount or 1))
            ).quantize(money_quantum, rounding=ROUND_HALF_UP)
        refund_total = -(total + refund_tax)
        refund_method = data.refund_method or original_sale.payment_method
        refund_currency = await self.currency_from_base(
            data.company_id, refund_method, data.payment_currency_code, abs(refund_total),
            at=datetime.now(timezone.utc),
        )
        refund_original = -Decimal(refund_currency["original_amount"])
        refund_sale = Sale(
            id=refund_id,
            company_id=data.company_id,
            original_sale_id=original_sale.id,
            shop_id=original_sale.shop_id,
            branch_id=branch.id,
            device_id=shift.device_id if shift else (data.device_id or original_sale.device_id),
            employee_id=shift.employee_id if shift else (data.employee_id or original_sale.employee_id),
            cashier_name=getattr(actor.employee, "name", None) if actor and actor.actor_type == "employee" else original_sale.cashier_name,
            shift_id=shift.id if shift else None,
            base_currency_code=refund_currency["base_currency"].code,
            payment_currency_code=refund_currency["currency"].code,
            exchange_rate_id=refund_currency["exchange_rate_id"],
            exchange_rate_snapshot=refund_currency["exchange_rate_snapshot"],
            payment_amount_original=refund_original,
            tendered_amount_original=refund_original,
            change_amount_original=Decimal("0"),
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
            tax_amount=-refund_tax,
            tax_inclusive=original_sale.tax_inclusive,
            total_amount=refund_total,
            amount_received=Decimal("0.00"),
            change_due=Decimal("0.00"),
            payment_method=refund_method,
            status="refunded",
            refund_reason=data.reason.strip(),
            refund_method=refund_method,
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
        actor=None,
    ):
        if actor is not None and actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            return await self.repo.list_sales(company_id, limit, branch_id=actor.employee.branch_id)
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
                has_sales_permission = has_permission(permissions, "sales_receipt_reprint" if mark_reprint else "sales_history_view")
                has_refunds_permission = has_permission(permissions, "sales_refund")
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
        if actor is not None:
            enforce_actor_branch(actor, sale.branch_id)

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
