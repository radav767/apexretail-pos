import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.currencies.service import quantize_currency
from app.auth.security import create_offline_shift_token, decode_offline_shift_token
from app.financial_access import enforce_actor_branch, enforce_actor_company
from app.models import (
    AuditEvent, Branch, CashierShift, CashierShiftCashMovement,
    CashierShiftCurrencySnapshot, Company, CreditSettlement, CurrencyExchangeRate,
    Device, Expense, OfflineSaleResolution, Sale, SaleItem, Shop,
)
from app.sales.repository import SalesRepository
from app.sales.service import SalesService
from app.employees.manager_approval import consume_manager_authorization
from app.employees.permissions import has_permission, normalize_permissions
from app.shifts.repository import ShiftRepository
from app.shifts.schema import CashMovementCreate


SUMMARY_FIELDS = (
    "gross_sales_base", "net_sales_base", "cost_of_sales_base", "gross_profit_base",
    "discounts_base", "cash_sales_base", "card_sales_base", "mobile_sales_base",
    "credit_sales_base", "cash_settlements_base", "card_settlements_base",
    "mobile_settlements_base", "cash_expenses_base", "noncash_expenses_base",
    "cash_refunds_base", "refunds_base", "cash_in_base", "cash_out_base",
)


class ShiftService:
    def __init__(self, repo: ShiftRepository):
        self.repo = repo

    @staticmethod
    def require_pos_actor(actor):
        if actor.actor_type != "employee" or actor.employee is None or actor.pos_session is None:
            raise HTTPException(401, "A valid opaque POS session is required")
        session = actor.pos_session
        if session.employee_id != actor.employee.id or session.company_id != actor.company_id:
            raise HTTPException(403, "POS session identity mismatch")
        return session

    async def view(self, shift, *, detailed=False, identity=None, include_offline_token=False):
        tips = getattr(shift, "tips_snapshot", None) if shift.status == "closed" else await self.repo.tip_summary(shift.id)
        snapshots = await self.repo.snapshots(shift.id)
        currencies = []
        for row in snapshots:
            if shift.status == "open":
                cash_sales, cash_refunds, cash_settlements, cash_expenses, cash_in, cash_out = await self._currency_activity(
                    shift.id, row.currency_code
                )
                expected_cash = row.opening_float + cash_sales + cash_settlements + cash_in - cash_refunds - cash_expenses - cash_out
                counted_cash = None
                variance = None
            else:
                cash_sales = row.cash_sales or Decimal("0")
                cash_refunds = row.cash_refunds or Decimal("0")
                cash_settlements = row.cash_settlements or Decimal("0")
                cash_expenses = row.cash_expenses or Decimal("0")
                movement_totals = await self.repo.cash_movement_totals(shift.id, row.currency_code)
                cash_in = row.cash_in if row.cash_in is not None else Decimal(movement_totals["cash_in"] or 0)
                cash_out = row.cash_out if row.cash_out is not None else Decimal(movement_totals["cash_out"] or 0)
                expected_cash = row.expected_cash if row.expected_cash is not None else row.opening_float
                counted_cash = row.counted_cash
                variance = row.variance
            currencies.append({
                "currency_code": row.currency_code,
                "currency_name": row.currency_name_snapshot,
                "symbol": row.currency_symbol_snapshot,
                "decimal_places": row.decimal_places_snapshot,
                "cash_accepted": row.cash_accepted_snapshot,
                "opening_float": row.opening_float,
                "cash_sales": cash_sales,
                "cash_refunds": cash_refunds,
                "cash_settlements": cash_settlements,
                "cash_expenses": cash_expenses,
                "cash_in": cash_in,
                "cash_out": cash_out,
                "cash_paid_out": cash_refunds + cash_expenses + cash_out,
                "expected_cash": quantize_currency(expected_cash, row.decimal_places_snapshot),
                "counted_cash": counted_cash,
                "variance": variance,
            })
        summary = {name: getattr(shift, name, None) for name in SUMMARY_FIELDS}
        summary["total_sales_base"] = summary["net_sales_base"]
        calculated_summary = None
        if detailed or shift.status == "open":
            calculated_summary = await self._base_summary(shift.id)
            if shift.status == "open":
                # Repositories and integrations predating Phase 4 may return
                # only the Phase 3 summary keys.  Treat newly additive totals
                # as zero instead of making an otherwise valid open shift
                # unreadable during a rolling deployment.
                summary.update({
                    name: calculated_summary.get(name, Decimal("0"))
                    for name in SUMMARY_FIELDS
                })
                summary["total_sales_base"] = summary["net_sales_base"]
        if detailed:
            summary.update({
                "total_sales_base": summary["net_sales_base"],
                "cash_received_base": calculated_summary["cash_received_base"] if shift.status=='open' else (summary['cash_sales_base'] or Decimal(0))+(summary['cash_settlements_base'] or Decimal(0)),
                "cash_paid_out_base": calculated_summary["cash_paid_out_base"] if shift.status=='open' else (summary['cash_refunds_base'] or Decimal(0))+(summary['cash_expenses_base'] or Decimal(0)),
                "refunds_base": calculated_summary["refunds_base"] if shift.status=='open' else summary['refunds_base'],
                "base_currency_code": await self.repo.base_currency_code(shift.company_id),
            })
        summary["base_currency_code"] = getattr(
            shift, "base_currency_code_snapshot", summary.get("base_currency_code")
        )
        movements = await self.repo.cash_movements(shift.id) if detailed else []
        if identity is None:
            identity = await self.repo.identity(shift)
        snapshot_identity = {
            "cashier_name": getattr(shift, "cashier_name_snapshot", None) or identity.get("cashier_name"),
            "shop_name": getattr(shift, "shop_name_snapshot", None) or identity.get("shop_name"),
            "branch_name": getattr(shift, "branch_name_snapshot", None) or identity.get("branch_name"),
            "register_name": getattr(shift, "register_name_snapshot", None) or identity.get("register_name"),
        }
        return {
            **{name: getattr(shift, name) for name in (
                "id", "shift_number", "company_id", "shop_id", "branch_id", "device_id",
                "employee_id", "status", "opened_at", "closed_at", "opening_note", "closing_note",
            )},
            **identity,
            **snapshot_identity,
            "business_name": getattr(shift, "business_name_snapshot", None),
            "closing_user_name": getattr(shift, "closing_user_name_snapshot", None),
            "report_generated_at": getattr(shift, "report_generated_at", None),
            "offline_shift_token": create_offline_shift_token(
                shift_id=str(shift.id), company_id=str(shift.company_id),
                branch_id=str(shift.branch_id), device_id=str(shift.device_id),
                employee_id=str(shift.employee_id), opened_at=shift.opened_at.isoformat(),
            ) if include_offline_token and shift.status == "open" else None,
            "currencies": currencies,
            "cash_movements": movements,
            "summary": summary,
            "tips": tips,
        }

    async def open(self, data, actor):
        session = self.require_pos_actor(actor)
        if not has_permission(normalize_permissions(actor.role, actor.permissions), "shifts_open"):
            raise HTTPException(403, "Shift opening permission denied")
        command_proof = None
        if hasattr(self.repo, 'begin_command'):
            committed, command_proof = await self.repo.begin_command(data, actor, 'open')
            if committed:
                return await self.view(await self.repo.by_id(actor.company_id, committed.shift_id), include_offline_token=True)
        existing_key = await self.repo.by_open_key(actor.company_id, data.idempotency_key.strip())
        if existing_key:
            if command_proof is not None:
                raise HTTPException(409, 'Historical shift opening has no complete replay proof; retrieve the original shift')
            if existing_key.employee_id != actor.employee.id or existing_key.device_id != session.device_id:
                raise HTTPException(409, "Shift idempotency key is already in use")
            return await self.view(existing_key, include_offline_token=True)
        existing = await self.repo.current(actor.employee.id, session.device_id, company_id=actor.company_id, for_update=True)
        if existing:
            raise HTTPException(409, "This cashier or register already has an open shift")
        currencies = await self.repo.active_currencies(actor.company_id)
        if not currencies:
            raise HTTPException(409, "No active company currencies are configured")
        opening = {row.currency_code: Decimal(row.amount) for row in data.opening_balances}
        if len(opening) != len(data.opening_balances):
            raise HTTPException(400, "Each opening currency may appear only once")
        known = {row.code for row in currencies}
        unknown = sorted(set(opening) - known)
        if unknown:
            raise HTTPException(400, f"Unknown opening currency: {unknown[0]}")
        for currency in currencies:
            if currency.code in opening and quantize_currency(opening[currency.code], currency.decimal_places) != opening[currency.code]:
                raise HTTPException(400, f"{currency.code} opening amount has too many decimal places")
            if not currency.cash_accepted and opening.get(currency.code, Decimal("0")) != 0:
                raise HTTPException(400, f"{currency.code} is not enabled for cash")
        shift_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        company = await self.repo.db.get(Company, actor.company_id)
        shop = await self.repo.db.get(Shop, session.shop_id)
        branch = await self.repo.db.get(Branch, session.branch_id)
        device = await self.repo.db.get(Device, session.device_id)
        shift = CashierShift(
            id=shift_id, shift_number=f"SHF-{now:%Y%m%d}-{str(shift_id)[:8].upper()}",
            company_id=actor.company_id, shop_id=session.shop_id, branch_id=session.branch_id,
            device_id=session.device_id, employee_id=actor.employee.id,
            opened_pos_session_id=session.id, status="open", opened_at=now,
            business_name_snapshot=company.name,
            shop_name_snapshot=shop.name,
            branch_name_snapshot=branch.name,
            register_name_snapshot=device.friendly_name or device.name or f"Register {device.pos_number}",
            cashier_name_snapshot=actor.employee.name,
            base_currency_code_snapshot=next(row.code for row in currencies if row.is_base),
            opening_note=(data.opening_note or "").strip() or None,
            open_idempotency_key=data.idempotency_key.strip(),
        )
        snapshots = [CashierShiftCurrencySnapshot(
            shift_id=shift.id, company_id=shift.company_id, company_currency_id=currency.id,
            currency_code=currency.code, currency_name_snapshot=currency.display_name,
            currency_symbol_snapshot=currency.symbol, decimal_places_snapshot=currency.decimal_places,
            cash_accepted_snapshot=currency.cash_accepted, card_accepted_snapshot=currency.card_accepted,
            mobile_accepted_snapshot=currency.mobile_accepted,
            opening_float=quantize_currency(opening.get(currency.code, Decimal("0")), currency.decimal_places),
        ) for currency in currencies]
        audit = AuditEvent(
            company_id=shift.company_id, actor_employee_id=shift.employee_id, device_id=shift.device_id,
            action="cashier_shift_opened", details={"shift_id": str(shift.id), "shift_number": shift.shift_number},
        )
        self.repo.db.add_all([shift, *snapshots, audit])
        if command_proof is not None:
            self.repo.record_command(command_proof, shift.id)
        try:
            await self.repo.db.commit()
        except IntegrityError as exc:
            await self.repo.db.rollback()
            raise HTTPException(409, "This cashier or register already has an open shift") from exc
        return await self.view(shift, detailed=True, include_offline_token=True)

    async def current(self, actor):
        session = self.require_pos_actor(actor)
        shift = await self.repo.current(actor.employee.id, session.device_id, company_id=actor.company_id)
        return await self.view(shift, detailed=True, include_offline_token=True) if shift else None

    async def _currency_activity(self, shift_id, code):
        db = self.repo.db
        from .split_accounting import activity
        split=await activity(db,shift_id,code)
        sales = list((await db.execute(select(Sale).where(
            Sale.shift_id == shift_id, Sale.payment_currency_code == code,
            Sale.payment_method == "cash",
        ))).scalars())
        cash_sales = sum((
            Decimal(row.tendered_amount_original or row.payment_amount_original or row.total_amount or 0)
            - Decimal(row.change_amount_original or 0)
            for row in sales if Decimal(row.total_amount or 0) >= 0
        ), Decimal("0"))
        cash_sales+=split['cash_original']
        cash_refunds = sum((abs(Decimal(row.payment_amount_original or row.total_amount or 0)) for row in sales if Decimal(row.total_amount or 0) < 0), Decimal("0"))+split['cash_refund_original']
        settlements = (await db.execute(select(func.coalesce(func.sum(CreditSettlement.original_amount), 0)).where(
            CreditSettlement.shift_id == shift_id, CreditSettlement.payment_currency_code == code,
            CreditSettlement.payment_method == "cash",
        ))).scalar_one()
        expenses = (await db.execute(select(func.coalesce(func.sum(Expense.original_amount), 0)).where(
            Expense.shift_id == shift_id, Expense.currency_code == code, Expense.payment_method == "cash",
        ))).scalar_one()
        movements = await self.repo.cash_movement_totals(shift_id, code)
        return tuple(Decimal(value or 0) for value in (
            cash_sales, cash_refunds, settlements, expenses,
            movements["cash_in"], movements["cash_out"],
        ))

    async def _base_summary(self, shift_id):
        db = self.repo.db
        from .split_accounting import activity
        split=await activity(db,shift_id)
        sales = list((await db.execute(select(Sale).where(Sale.shift_id == shift_id))).scalars())
        gross = sum((Decimal(row.total_amount or 0) + Decimal(row.discount_amount or 0) for row in sales if row.original_sale_id is None), Decimal("0"))
        net = sum((Decimal(row.total_amount or 0) for row in sales), Decimal("0"))
        discounts = sum((Decimal(row.discount_amount or 0) for row in sales if row.original_sale_id is None), Decimal("0"))
        by_method = {name: sum((Decimal(row.total_amount or 0) for row in sales if row.payment_method == name and row.original_sale_id is None), Decimal("0")) for name in ("cash", "card", "mobile", "credit")}
        by_method['cash']+=split['cash_base'];by_method['credit']+=split['credit_base']
        sale_ids = [row.id for row in sales]
        cost = Decimal("0")
        if sale_ids:
            cost = Decimal((await db.execute(select(func.coalesce(func.sum(SaleItem.line_cost), 0)).where(SaleItem.sale_id.in_(sale_ids)))).scalar_one() or 0)
        settlements = {name: Decimal((await db.execute(select(func.coalesce(func.sum(CreditSettlement.amount), 0)).where(CreditSettlement.shift_id == shift_id, CreditSettlement.payment_method == name))).scalar_one() or 0) for name in ("cash", "card", "mobile")}
        cash_expenses = Decimal((await db.execute(select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.shift_id == shift_id, Expense.payment_method == "cash"))).scalar_one() or 0)
        noncash_expenses = Decimal((await db.execute(select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.shift_id == shift_id, Expense.payment_method.in_(("card", "mobile"))))).scalar_one() or 0)
        cash_in = Decimal((await db.execute(select(func.coalesce(func.sum(CashierShiftCashMovement.base_amount), 0)).where(CashierShiftCashMovement.shift_id == shift_id, CashierShiftCashMovement.movement_type == "cash_in"))).scalar_one() or 0)
        cash_out = Decimal((await db.execute(select(func.coalesce(func.sum(CashierShiftCashMovement.base_amount), 0)).where(CashierShiftCashMovement.shift_id == shift_id, CashierShiftCashMovement.movement_type == "cash_out"))).scalar_one() or 0)
        cash_received = by_method['cash'] + settlements["cash"]
        refunds = sum((abs(Decimal(row.total_amount or 0)) for row in sales if row.original_sale_id is not None and Decimal(row.total_amount or 0) < 0), Decimal("0"))
        cash_refunds = sum((abs(Decimal(row.total_amount or 0)) for row in sales if row.original_sale_id is not None and row.payment_method == "cash" and Decimal(row.total_amount or 0) < 0), Decimal("0"))+split['cash_refund_base']
        return {
            "gross_sales_base": gross, "net_sales_base": net, "cost_of_sales_base": cost,
            "gross_profit_base": net - cost, "discounts_base": discounts,
            "cash_sales_base": by_method["cash"], "card_sales_base": by_method["card"],
            "mobile_sales_base": by_method["mobile"], "credit_sales_base": by_method["credit"],
            "cash_settlements_base": settlements["cash"], "card_settlements_base": settlements["card"],
            "mobile_settlements_base": settlements["mobile"], "cash_expenses_base": cash_expenses,
            "noncash_expenses_base": noncash_expenses,
            "cash_received_base": cash_received,
            "cash_paid_out_base": cash_refunds + cash_expenses,
            "refunds_base": refunds,
            "cash_refunds_base": cash_refunds,
            "cash_in_base": cash_in,
            "cash_out_base": cash_out,
        }

    async def close(self, shift_id, data, actor):
        session = self.require_pos_actor(actor)
        if not has_permission(normalize_permissions(actor.role, actor.permissions), "shifts_close"):
            raise HTTPException(403, "Shift closing permission denied")
        if not data.confirmed:
            raise HTTPException(400, "Shift closure must be confirmed")
        shift = await self.repo.by_id(actor.company_id, shift_id, for_update=True)
        if shift is None:
            raise HTTPException(404, "Shift not found")
        if shift.employee_id != actor.employee.id or shift.device_id != session.device_id:
            raise HTTPException(403, "Only the shift cashier on this register may close the shift")
        command_proof = None
        if hasattr(self.repo, 'begin_command'):
            committed, command_proof = await self.repo.begin_command(data, actor, 'close', shift)
            if committed: return await self.view(shift, detailed=True)
        if shift.status == "closed":
            if command_proof is not None:
                raise HTTPException(409, 'Historical shift closure has no complete replay proof; retrieve the original shift')
            if shift.close_idempotency_key == data.idempotency_key.strip():
                return await self.view(shift, detailed=True)
            raise HTTPException(409, "Shift is already closed")
        snapshots = await self.repo.snapshots(shift.id, for_update=True)
        counted = {row.currency_code: Decimal(row.amount) for row in data.counted_balances}
        required = {row.currency_code for row in snapshots if row.cash_accepted_snapshot}
        if set(counted) != required:
            raise HTTPException(400, "A closing cash count is required for every enabled cash currency")
        for row in snapshots:
            cash_sales, cash_refunds, settlements, expenses, cash_in, cash_out = await self._currency_activity(shift.id, row.currency_code)
            quantum = row.decimal_places_snapshot
            if row.cash_accepted_snapshot and quantize_currency(counted[row.currency_code], quantum) != counted[row.currency_code]:
                raise HTTPException(400, f"{row.currency_code} closing count has too many decimal places")
            row.cash_sales = quantize_currency(cash_sales, quantum)
            row.cash_refunds = quantize_currency(cash_refunds, quantum)
            row.cash_settlements = quantize_currency(settlements, quantum)
            row.cash_expenses = quantize_currency(expenses, quantum)
            row.cash_in = quantize_currency(cash_in, quantum)
            row.cash_out = quantize_currency(cash_out, quantum)
            row.expected_cash = quantize_currency(row.opening_float + cash_sales + settlements + cash_in - cash_refunds - expenses - cash_out, quantum)
            if row.cash_accepted_snapshot:
                row.counted_cash = quantize_currency(counted[row.currency_code], quantum)
                row.variance = quantize_currency(row.counted_cash - row.expected_cash, quantum)
        # Persist closing currency figures while the parent is still open;
        # the database trigger rejects any snapshot mutation after closure.
        await self.repo.db.flush(snapshots)
        base_summary = await self._base_summary(shift.id)
        for name in SUMMARY_FIELDS:
            value = base_summary[name]
            setattr(shift, name, value.quantize(Decimal("0.01")))
        shift.tips_snapshot = await self.repo.tip_summary(shift.id)
        shift.status = "closed"
        shift.closed_at = datetime.now(timezone.utc)
        shift.closing_note = (data.closing_note or "").strip() or None
        shift.close_idempotency_key = data.idempotency_key.strip()
        shift.closed_by_employee_id = actor.employee.id
        shift.closing_user_name_snapshot = actor.employee.name
        shift.report_generated_at = shift.closed_at
        self.repo.db.add(AuditEvent(
            company_id=shift.company_id, actor_employee_id=shift.employee_id, device_id=shift.device_id,
            action="cashier_shift_closed", details={"shift_id": str(shift.id), "shift_number": shift.shift_number},
        ))
        if command_proof is not None:
            self.repo.record_command(command_proof, shift.id)
        await self.repo.db.commit()
        return await self.view(shift, detailed=True)

    @staticmethod
    def _can_manage_shifts(actor):
        return actor.role in {"owner", "administrator", "manager"} or bool((actor.permissions or {}).get("shifts_manage")) or (
            has_permission(actor.permissions, "approve_restricted_actions")
            and has_permission(actor.permissions, "shifts_close")
        )

    async def manager_close(self, shift_id, data, actor):
        if actor.company_id is None or not self._can_manage_shifts(actor):
            raise HTTPException(403, "Shift management permission denied")
        if not data.confirmed or not (data.exception_reason or "").strip():
            raise HTTPException(400, "A confirmed exception reason is required")
        shift = await self.repo.by_id(actor.company_id, shift_id, for_update=True)
        if shift is None:
            raise HTTPException(404, "Shift not found")
        if actor.actor_type == "employee":
            enforce_actor_branch(actor, shift.branch_id)
        command_proof = None
        if hasattr(self.repo, 'begin_command'):
            committed, command_proof = await self.repo.begin_command(data, actor, 'manager_close', shift)
            if committed: return await self.view(shift, detailed=True)
        if shift.status == "closed":
            if command_proof is not None:
                raise HTTPException(409, 'Historical shift closure has no complete replay proof; retrieve the original shift')
            if shift.close_idempotency_key == data.idempotency_key.strip():
                return await self.view(shift, detailed=True)
            raise HTTPException(409, "Shift is already closed")
        snapshots = await self.repo.snapshots(shift.id, for_update=True)
        counted = {row.currency_code: Decimal(row.amount) for row in data.counted_balances}
        required = {row.currency_code for row in snapshots if row.cash_accepted_snapshot}
        if set(counted) != required:
            raise HTTPException(400, "A closing cash count is required for every enabled cash currency")
        for row in snapshots:
            sales, refunds, settlements, expenses, cash_in, cash_out = await self._currency_activity(shift.id, row.currency_code)
            precision = row.decimal_places_snapshot
            row.cash_sales = quantize_currency(sales, precision)
            row.cash_refunds = quantize_currency(refunds, precision)
            row.cash_settlements = quantize_currency(settlements, precision)
            row.cash_expenses = quantize_currency(expenses, precision)
            row.cash_in = quantize_currency(cash_in, precision)
            row.cash_out = quantize_currency(cash_out, precision)
            row.expected_cash = quantize_currency(row.opening_float + sales + settlements + cash_in - refunds - expenses - cash_out, precision)
            if row.cash_accepted_snapshot:
                row.counted_cash = quantize_currency(counted[row.currency_code], precision)
                row.variance = quantize_currency(row.counted_cash - row.expected_cash, precision)
        await self.repo.db.flush(snapshots)
        base_summary = await self._base_summary(shift.id)
        for name in SUMMARY_FIELDS:
            setattr(shift, name, base_summary[name].quantize(Decimal("0.01")))
        now = datetime.now(timezone.utc)
        shift.tips_snapshot = await self.repo.tip_summary(shift.id)
        shift.status, shift.closed_at, shift.report_generated_at = "closed", now, now
        shift.closing_note = (data.closing_note or "").strip() or None
        shift.close_idempotency_key = data.idempotency_key.strip()
        shift.closed_by_user_id = actor.user.id if actor.actor_type == "user" and actor.user else None
        shift.closed_by_employee_id = actor.employee.id if actor.actor_type == "employee" and actor.employee else None
        shift.closing_user_name_snapshot = actor.user.email if actor.actor_type == "user" and actor.user else actor.employee.name
        self.repo.db.add(AuditEvent(
            company_id=shift.company_id, actor_user_id=shift.closed_by_user_id,
            actor_employee_id=shift.closed_by_employee_id, device_id=shift.device_id,
            action="cashier_shift_manager_closed", reason=data.exception_reason.strip(),
            details={"shift_id": str(shift.id), "shift_number": shift.shift_number},
        ))
        if command_proof is not None:
            self.repo.record_command(command_proof, shift.id)
        await self.repo.db.commit()
        return await self.view(shift, detailed=True)

    @staticmethod
    def _movement_output(movement, actor_name=None):
        return {
            "id": movement.id, "company_id": movement.company_id, "shift_id": movement.shift_id,
            "branch_id": movement.branch_id, "device_id": movement.device_id,
            "employee_id": movement.employee_id, "actor_name": actor_name,
            "movement_type": movement.movement_type, "currency_code": movement.currency_code,
            "amount": movement.amount, "base_amount": movement.base_amount,
            "exchange_rate_snapshot": movement.exchange_rate_snapshot, "reason": movement.reason,
            "idempotency_key": movement.idempotency_key, "created_at": movement.created_at,
        }

    @staticmethod
    def _movement_matches(movement, shift, actor, data):
        return (
            movement.shift_id == shift.id and movement.employee_id == actor.employee.id
            and movement.company_id == actor.company_id
            and movement.device_id == actor.pos_session.device_id
            and movement.branch_id == actor.pos_session.branch_id
            and movement.movement_type == data.movement_type
            and movement.currency_code == data.currency_code
            and movement.amount == data.amount and movement.reason == data.reason
        )

    async def create_cash_movement(self, shift_id, data: CashMovementCreate, actor):
        session = self.require_pos_actor(actor)
        key = data.idempotency_key
        if key.startswith('tip:'):
            raise HTTPException(422, 'Tip command identities are reserved for the original tip ledger')
        shift = await self.repo.by_id(actor.company_id, shift_id, for_update=True)
        if shift is None: raise HTTPException(404, 'Shift not found')
        if shift.employee_id != actor.employee.id or shift.device_id != session.device_id or shift.branch_id != session.branch_id:
            raise HTTPException(403, 'Only the cashier on this register may record shift cash movements')
        command_proof = None
        if hasattr(self.repo, 'begin_command'):
            committed, command_proof = await self.repo.begin_command(data, actor, 'cash', shift)
            if committed:
                existing = await self.repo.cash_movement_by_key(actor.company_id, key)
                if existing is None or existing.id != committed.movement_id:
                    raise HTTPException(409, 'Original cash movement requires review')
                return self._movement_output(existing, actor.employee.name)
        existing = await self.repo.cash_movement_by_key(actor.company_id, key)
        if existing is not None:
            if command_proof is None and self._movement_matches(existing, shift, actor, data):
                return self._movement_output(existing, actor.employee.name)
            raise HTTPException(409, 'Historical cash command has no complete replay proof; retrieve the original movement')
        if shift.status != 'open':
            raise HTTPException(409, 'Cash movements can only be recorded during an open shift')
        if not has_permission(normalize_permissions(actor.role, actor.permissions), 'cash_movements_manage'):
            await consume_manager_authorization(
                self.repo.db, actor, data.manager_authorization_token, 'cash_movement', {
                    'shift_id':str(shift_id), 'movement_type':data.movement_type,
                    'currency_code':data.currency_code, 'amount':str(data.amount),
                },
            )

        snapshots = await self.repo.snapshots(shift.id, for_update=True)
        snapshot = next((row for row in snapshots if row.currency_code == data.currency_code), None)
        if snapshot is None or not snapshot.cash_accepted_snapshot:
            raise HTTPException(400, "This currency is not enabled for cash on this shift")
        amount = Decimal(data.amount)
        normalized_amount = quantize_currency(amount, snapshot.decimal_places_snapshot)
        if normalized_amount != amount:
            raise HTTPException(400, f"Amount must use {snapshot.decimal_places_snapshot} decimal places or fewer")
        if data.movement_type == "cash_out":
            sales, refunds, settlements, expenses, cash_in, cash_out = await self._currency_activity(shift.id, data.currency_code)
            available = snapshot.opening_float + sales + settlements + cash_in - refunds - expenses - cash_out
            if amount > available:
                raise HTTPException(409, "Cash out exceeds the expected drawer balance")

        currency = next((row for row in await self.repo.active_currencies(actor.company_id) if row.code == data.currency_code), None)
        if currency is None:
            raise HTTPException(409, "The shift currency is no longer active")
        now = datetime.now(timezone.utc)
        if currency.is_base:
            rate = Decimal("1")
        else:
            rate_row = (await self.repo.db.execute(select(CurrencyExchangeRate).where(
                CurrencyExchangeRate.company_id == actor.company_id,
                CurrencyExchangeRate.currency_id == currency.id,
                CurrencyExchangeRate.effective_at <= now,
            ).order_by(CurrencyExchangeRate.effective_at.desc(), CurrencyExchangeRate.created_at.desc()).limit(1))).scalar_one_or_none()
            rate = Decimal(rate_row.foreign_units_per_base) if rate_row is not None else None

        movement = CashierShiftCashMovement(
            id=uuid.uuid4(),
            company_id=shift.company_id, shift_id=shift.id, branch_id=shift.branch_id,
            device_id=shift.device_id, employee_id=actor.employee.id,
            movement_type=data.movement_type, currency_code=data.currency_code,
            amount=normalized_amount,
            base_amount=(normalized_amount / rate).quantize(Decimal("0.01")) if rate is not None else None,
            exchange_rate_snapshot=rate,
            reason=data.reason, idempotency_key=key,
        )
        self.repo.db.add(movement)
        self.repo.db.add(AuditEvent(
            company_id=shift.company_id, actor_employee_id=actor.employee.id,
            device_id=shift.device_id, action=f"cashier_shift_{data.movement_type}",
            details={"shift_id": str(shift.id), "movement_id": str(movement.id), "currency_code": data.currency_code, "amount": str(normalized_amount)},
        ))
        if command_proof is not None:
            self.repo.record_command(command_proof, shift.id, movement_id=movement.id)
        try:
            await self.repo.db.commit()
        except IntegrityError as exc:
            await self.repo.db.rollback()
            if command_proof is not None:
                raise HTTPException(409, 'Cash movement identity conflict; retrieve the original movement') from exc
            existing = await self.repo.cash_movement_by_key(actor.company_id, key)
            if existing is not None:
                shift = await self.repo.by_id(actor.company_id, existing.shift_id)
                if shift is not None and self._movement_matches(existing, shift, actor, data):
                    return self._movement_output(existing, actor.employee.name)
            raise HTTPException(409, "Cash movement conflicted with another request") from exc
        await self.repo.db.refresh(movement)
        return self._movement_output(movement, actor.employee.name)

    async def add_movement(self, data: CashMovementCreate, actor):
        session = self.require_pos_actor(actor)
        if hasattr(self.repo, 'begin_command'):
            original = await self.repo.cash_movement_by_key(actor.company_id, data.idempotency_key)
            if original is not None:
                result = await self.create_cash_movement(original.shift_id, data, actor)
                return SimpleNamespace(**result) if isinstance(result, dict) else result
        shift = await self.repo.current(actor.employee.id, session.device_id, company_id=actor.company_id)
        if shift is None:
            raise HTTPException(409, "An active shift for this cashier and register is required")
        result = await self.create_cash_movement(shift.id, data, actor)
        return SimpleNamespace(**result) if isinstance(result, dict) else result

    async def preview_close(self, actor):
        session = self.require_pos_actor(actor)
        shift = await self.repo.current(actor.employee.id, session.device_id, company_id=actor.company_id)
        if shift is None:
            raise HTTPException(404, "No active shift")
        return await self.view(shift, detailed=True, include_offline_token=True)

    async def manager_preview_close(self, shift_id, actor):
        if not self._can_manage_shifts(actor):
            raise HTTPException(403, "Shift management permission denied")
        shift = await self.repo.by_id(actor.company_id, shift_id)
        if shift is None:
            raise HTTPException(404, "Shift not found")
        if actor.actor_type == "employee":
            enforce_actor_branch(actor, shift.branch_id)
        return await self.view(shift, detailed=True)

    async def my_history(self, actor, *, page=1, page_size=10):
        session = self.require_pos_actor(actor)
        enforce_actor_company(actor, actor.company_id)
        rows, total = await self.repo.list(
            actor.company_id, branch_id=session.branch_id, employee_id=actor.employee.id,
            device_id=session.device_id, limit=page_size, offset=(page - 1) * page_size,
        )
        identities = await self.repo.identities(rows)
        return [await self.view(row, identity=identities.get(row.id)) for row in rows], total

    async def my_detail(self, shift_id, actor):
        session = self.require_pos_actor(actor)
        shift = await self.repo.by_id(actor.company_id, shift_id)
        if shift is None:
            raise HTTPException(404, "Shift not found")
        if shift.employee_id != actor.employee.id or shift.device_id != session.device_id or shift.branch_id != session.branch_id:
            raise HTTPException(403, "Shift belongs to another cashier or register")
        return await self.view(shift, detailed=True)

    async def history(self, company_id, actor, **filters):
        enforce_actor_company(actor, company_id)
        if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            if filters.get("branch_id") is not None:
                enforce_actor_branch(actor, filters["branch_id"])
            filters["branch_id"] = actor.employee.branch_id
        rows, total = await self.repo.list(company_id, **filters)
        identities = await self.repo.identities(rows)
        return [await self.view(row, identity=identities.get(row.id)) for row in rows], total

    async def report_summary(self, company_id, actor, **filters):
        filters = self._report_scope(company_id, actor, filters)
        return await self.repo.report_summary(company_id, **filters)

    async def filter_options(self, company_id, actor):
        branch_id = None
        enforce_actor_company(actor, company_id)
        if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            if actor.employee is None:
                raise HTTPException(403, "Branch access denied")
            branch_id = actor.employee.branch_id
        return await self.repo.filter_options(company_id, branch_id=branch_id)

    async def detail(self, company_id, shift_id, actor):
        enforce_actor_company(actor, company_id)
        shift = await self.repo.by_id(company_id, shift_id)
        if shift is None:
            raise HTTPException(404, "Shift not found")
        if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            if actor.employee is None or shift.branch_id != actor.employee.branch_id:
                raise HTTPException(403, "Branch access denied")
        return await self.view(shift, detailed=True)

    def _report_scope(self, company_id, actor, filters):
        enforce_actor_company(actor, company_id)
        scoped = dict(filters)
        if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            if actor.employee is None:
                raise HTTPException(403, "Branch access denied")
            if scoped.get("branch_id") is not None:
                enforce_actor_branch(actor, scoped["branch_id"])
            scoped["branch_id"] = actor.employee.branch_id
        return scoped

    async def export_history(self, company_id, actor, **filters):
        filters = self._report_scope(company_id, actor, filters)
        rows, total = await self.repo.list(company_id, limit=10001, offset=0, **filters)
        if total > 10000:
            raise HTTPException(413, "Narrow the filters to export at most 10,000 shifts at a time")
        identities = await self.repo.identities(rows)
        return [
            await self.view(row, identity=identities.get(row.id))
            for row in rows
        ], total

    async def z_report(self, shift_id, actor, *, reprint=False):
        enforce_actor_company(actor, actor.company_id)
        if actor.actor_type == "employee" and not has_permission(normalize_permissions(actor.role, actor.permissions), "z_reports_view"):
            raise HTTPException(403, "Z Report permission denied")
        shift = await self.repo.by_id(actor.company_id, shift_id)
        if shift is None:
            raise HTTPException(404, "Shift not found")
        if actor.actor_type == "employee" and shift.employee_id != actor.employee.id:
            if not self._can_manage_shifts(actor):
                raise HTTPException(403, "Shift report permission denied")
            enforce_actor_branch(actor, shift.branch_id)
        if shift.status != "closed":
            raise HTTPException(409, "Z Report is available only after shift closure")
        if reprint:
            self.repo.db.add(AuditEvent(
                company_id=shift.company_id,
                actor_user_id=actor.user.id if actor.actor_type == "user" and actor.user else None,
                actor_employee_id=actor.employee.id if actor.actor_type == "employee" and actor.employee else None,
                device_id=actor.pos_session.device_id if actor.pos_session else None,
                action="z_report_reprinted",
                details={"shift_id": str(shift.id), "shift_number": shift.shift_number},
            ))
            await self.repo.db.commit()
        # Closed shift summaries and currency rows are immutable snapshots.
        return await self.view(shift, detailed=False)

    @staticmethod
    def _resolution_view(row):
        return {
            "id": row.id, "company_id": row.company_id,
            "client_sale_id": row.client_sale_id,
            "original_shift_id": row.original_shift_id,
            "original_employee_id": row.original_employee_id,
            "original_device_id": row.original_device_id,
            "sale_id": row.sale_id, "action": row.action, "reason": row.reason,
            "payload_sha256": row.payload_sha256,
            "resolver_name": row.resolver_name_snapshot,
            "created_at": row.created_at,
        }

    async def resolve_offline_sale(self, data, actor):
        if not self._can_manage_shifts(actor):
            raise HTTPException(403, "Shift management permission denied")
        from app.sales.commands import actor_identity
        actor_identity(actor, actor.company_id)
        data = data.model_copy(deep=True)
        if len(data.reason.strip()) < 3: raise HTTPException(422, 'A review reason is required')
        sale_data = data.sale
        if sale_data.company_id != actor.company_id:
            raise HTTPException(403, "Offline sale company mismatch")
        if sale_data.client_sale_id is None or sale_data.shift_id is None or not sale_data.offline_shift_token:
            raise HTTPException(400, "Client sale ID, original shift ID, and offline shift token are required")
        if sale_data.client_created_at is None:
            raise HTTPException(400, "Original offline transaction timestamp is required")
        if sale_data.payment_method.strip().lower() == "credit":
            raise HTTPException(409, "Offline credit sales cannot be resolved")
        if hasattr(self.repo, 'begin_command'):
            # Same global sale-identity lock as normal sale submission, BEFORE
            # the original shift lock; never invert sale->shift lock ordering.
            await self.repo.db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                {'key':'phase11-sale:'+str(sale_data.client_sale_id)})
        try:
            # Expiry limits automatic sync, not audited manager review of an
            # already quarantined transaction. Signature and identity remain mandatory.
            token = decode_offline_shift_token(sale_data.offline_shift_token, verify_expiration=False)
            token_shift_id = UUID(str(token.get("shift_id")))
        except Exception as exc:
            raise HTTPException(409, "Offline shift identity is invalid") from exc
        if token_shift_id != sale_data.shift_id:
            raise HTTPException(409, "Offline shift identity does not match the sale")
        shift = await self.repo.by_id(actor.company_id, token_shift_id, for_update=True)
        if shift is None:
            raise HTTPException(404, "Original shift not found")
        expected_identity = {
            "company_id": shift.company_id, "branch_id": shift.branch_id,
            "device_id": shift.device_id, "employee_id": shift.employee_id,
        }
        if any(str(value) != str(token.get(name)) for name, value in expected_identity.items()):
            raise HTTPException(409, "Offline shift identity evidence does not match the original shift")
        if shift.status != "closed" or shift.closed_at is None:
            raise HTTPException(409, "The original shift must be closed before manager resolution")
        if sale_data.client_created_at < shift.opened_at or sale_data.client_created_at > shift.closed_at:
            raise HTTPException(409, "Offline sale timestamp falls outside the original shift")
        for supplied, expected, label in (
            (sale_data.branch_id, shift.branch_id, "branch"),
            (sale_data.employee_id, shift.employee_id, "cashier"),
            (sale_data.device_id, shift.device_id, "register"),
        ):
            if supplied is not None and supplied != expected:
                raise HTTPException(409, f"Offline sale {label} does not match the original shift")
        if actor.actor_type == "employee":
            enforce_actor_branch(actor, shift.branch_id)
        command_proof = None
        if hasattr(self.repo, 'begin_command'):
            committed, command_proof = await self.repo.begin_command(data, actor, 'resolution', shift)
            if committed:
                original = await self.repo.offline_resolution(actor.company_id, client_sale_id=sale_data.client_sale_id)
                if not original or original.id != committed.resolution_id:
                    raise HTTPException(409, 'Original resolution requires review')
                return self._resolution_view(original)
        existing = await self.repo.offline_resolution(actor.company_id, client_sale_id=sale_data.client_sale_id)
        if existing:
            if command_proof is None: return self._resolution_view(existing)
            raise HTTPException(409, 'Historical resolution has no complete replay proof; retrieve original evidence')
        if await SalesRepository(self.repo.db).get_by_client_sale_id(actor.company_id, sale_data.client_sale_id):
            raise HTTPException(409, 'Offline sale is already recorded and cannot be reviewed as quarantined')
        if await self.repo.offline_resolution(actor.company_id, idempotency_key=data.idempotency_key.strip()):
            raise HTTPException(409, 'Offline resolution idempotency key is already in use')
        payload = sale_data.model_dump(mode="json")
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        resolver_name = actor.user.email if actor.actor_type == "user" and actor.user else actor.employee.name
        resolution = OfflineSaleResolution(
            id=uuid.uuid4(), company_id=actor.company_id,
            client_sale_id=sale_data.client_sale_id,
            original_shift_id=shift.id, original_employee_id=shift.employee_id,
            original_device_id=shift.device_id, action=data.action,
            reason=data.reason.strip(), payload_sha256=digest,
            payload_snapshot=payload, idempotency_key=data.idempotency_key.strip(),
            resolved_by_user_id=actor.user.id if actor.actor_type == "user" and actor.user else None,
            resolved_by_employee_id=actor.employee.id if actor.actor_type == "employee" and actor.employee else None,
            resolver_name_snapshot=resolver_name,
        )
        audit = AuditEvent(
            company_id=actor.company_id,
            actor_user_id=resolution.resolved_by_user_id,
            actor_employee_id=resolution.resolved_by_employee_id,
            device_id=shift.device_id,
            action="offline_sale_retained_quarantined",
            reason=resolution.reason,
            details={
                "resolution_id": str(resolution.id),
                "client_sale_id": str(resolution.client_sale_id),
                "original_shift_id": str(shift.id), "payload_sha256": digest,
            },
        )
        resolution_receipt = self.repo.record_command(command_proof, shift.id, resolution_id=resolution.id, stage=False) if command_proof is not None else None
        if data.action == "retain_quarantined":
            self.repo.db.add_all([resolution, audit])
            if resolution_receipt is not None: self.repo.db.add(resolution_receipt)
            try:
                await self.repo.db.commit()
                await self.repo.db.refresh(resolution)
            except IntegrityError as exc:
                await self.repo.db.rollback()
                if command_proof is not None:
                    raise HTTPException(409, 'Resolution identity conflict; retrieve original evidence') from exc
                retry = await self.repo.offline_resolution(actor.company_id, client_sale_id=sale_data.client_sale_id)
                if retry:
                    return self._resolution_view(retry)
                raise HTTPException(409, "Offline sale was already reviewed") from exc
            return self._resolution_view(resolution)

        sale_data.branch_id = shift.branch_id
        sale_data.employee_id = shift.employee_id
        sale_data.device_id = shift.device_id
        sale_data.device_key = None
        sale_data.assignment_revision = None
        employee = SimpleNamespace(
            id=shift.employee_id, name=shift.cashier_name_snapshot,
            branch_id=shift.branch_id, role="cashier",
            permissions={"sales": True, "discounts": True},
        )
        device = SimpleNamespace(
            id=shift.device_id, name=shift.register_name_snapshot,
            friendly_name=shift.register_name_snapshot, pos_number=None,
        )
        try:
            await SalesService(SalesRepository(self.repo.db)).create_sale(
                sale_data, actor=actor, resolved_shift=shift,
                resolved_employee=employee, resolved_device=device,
                resolution_record=resolution,
                resolution_command_receipt=resolution_receipt,
            )
        except IntegrityError as exc:
            await self.repo.db.rollback()
            if command_proof is not None:
                raise HTTPException(409, 'Resolution identity conflict; retrieve original evidence') from exc
            retry = await self.repo.offline_resolution(actor.company_id, client_sale_id=sale_data.client_sale_id)
            if retry:
                return self._resolution_view(retry)
            raise HTTPException(409, "Offline sale was already reviewed or recorded") from exc
        await self.repo.db.refresh(resolution)
        return self._resolution_view(resolution)

    async def offline_resolution_history(self, company_id, actor, **filters):
        enforce_actor_company(actor, company_id)
        if actor.actor_type == "employee" and not self._can_manage_shifts(actor):
            raise HTTPException(403, "Shift management permission denied")
        rows, total = await self.repo.offline_resolutions(company_id, **filters)
        return [self._resolution_view(row) for row in rows], total
