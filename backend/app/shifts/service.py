import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.currencies.service import quantize_currency
from app.financial_access import enforce_actor_branch, enforce_actor_company
from app.models import (
    AuditEvent, CashierShift, CashierShiftCashMovement,
    CashierShiftCurrencySnapshot, CreditSettlement, Expense, Sale, SaleItem,
)
from app.shifts.repository import ShiftRepository
from app.shifts.schema import CashMovementCreate


SUMMARY_FIELDS = (
    "gross_sales_base", "net_sales_base", "cost_of_sales_base", "gross_profit_base",
    "discounts_base", "cash_sales_base", "card_sales_base", "mobile_sales_base",
    "credit_sales_base", "cash_settlements_base", "card_settlements_base",
    "mobile_settlements_base", "cash_expenses_base", "noncash_expenses_base",
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

    async def view(self, shift, *, detailed=False, identity=None):
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
        summary = {name: getattr(shift, name) for name in SUMMARY_FIELDS}
        summary["total_sales_base"] = summary["net_sales_base"]
        calculated_summary = None
        if detailed or shift.status == "open":
            calculated_summary = await self._base_summary(shift.id)
            if shift.status == "open":
                summary.update({name: calculated_summary[name] for name in SUMMARY_FIELDS})
                summary["total_sales_base"] = summary["net_sales_base"]
        if detailed:
            summary.update({
                "total_sales_base": summary["net_sales_base"],
                "cash_received_base": calculated_summary["cash_received_base"],
                "cash_paid_out_base": calculated_summary["cash_paid_out_base"],
                "refunds_base": calculated_summary["refunds_base"],
                "base_currency_code": await self.repo.base_currency_code(shift.company_id),
            })
        movements = await self.repo.cash_movements(shift.id) if detailed else []
        if identity is None:
            identity = await self.repo.identity(shift)
        return {
            **{name: getattr(shift, name) for name in (
                "id", "shift_number", "company_id", "shop_id", "branch_id", "device_id",
                "employee_id", "status", "opened_at", "closed_at", "opening_note", "closing_note",
            )},
            **identity,
            "currencies": currencies,
            "cash_movements": movements,
            "summary": summary,
        }

    async def open(self, data, actor):
        session = self.require_pos_actor(actor)
        existing_key = await self.repo.by_open_key(actor.company_id, data.idempotency_key.strip())
        if existing_key:
            if existing_key.employee_id != actor.employee.id or existing_key.device_id != session.device_id:
                raise HTTPException(409, "Shift idempotency key is already in use")
            return await self.view(existing_key)
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
        shift = CashierShift(
            id=shift_id, shift_number=f"SHF-{now:%Y%m%d}-{str(shift_id)[:8].upper()}",
            company_id=actor.company_id, shop_id=session.shop_id, branch_id=session.branch_id,
            device_id=session.device_id, employee_id=actor.employee.id,
            opened_pos_session_id=session.id, status="open", opened_at=now,
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
        try:
            await self.repo.db.commit()
        except IntegrityError as exc:
            await self.repo.db.rollback()
            raise HTTPException(409, "This cashier or register already has an open shift") from exc
        return await self.view(shift, detailed=True)

    async def current(self, actor):
        session = self.require_pos_actor(actor)
        shift = await self.repo.current(actor.employee.id, session.device_id, company_id=actor.company_id)
        return await self.view(shift, detailed=True) if shift else None

    async def _currency_activity(self, shift_id, code):
        db = self.repo.db
        sales = list((await db.execute(select(Sale).where(
            Sale.shift_id == shift_id, Sale.payment_currency_code == code,
            Sale.payment_method == "cash",
        ))).scalars())
        cash_sales = sum((Decimal(row.payment_amount_original or row.total_amount or 0) for row in sales if Decimal(row.total_amount or 0) >= 0), Decimal("0"))
        cash_refunds = sum((abs(Decimal(row.payment_amount_original or row.total_amount or 0)) for row in sales if Decimal(row.total_amount or 0) < 0), Decimal("0"))
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
        sales = list((await db.execute(select(Sale).where(Sale.shift_id == shift_id))).scalars())
        gross = sum((Decimal(row.total_amount or 0) for row in sales if row.original_sale_id is None), Decimal("0"))
        net = sum((Decimal(row.total_amount or 0) for row in sales), Decimal("0"))
        discounts = sum((Decimal(row.discount_amount or 0) for row in sales if row.original_sale_id is None), Decimal("0"))
        by_method = {name: sum((Decimal(row.total_amount or 0) for row in sales if row.payment_method == name), Decimal("0")) for name in ("cash", "card", "mobile", "credit")}
        sale_ids = [row.id for row in sales]
        cost = Decimal("0")
        if sale_ids:
            cost = Decimal((await db.execute(select(func.coalesce(func.sum(SaleItem.line_cost), 0)).where(SaleItem.sale_id.in_(sale_ids)))).scalar_one() or 0)
        settlements = {name: Decimal((await db.execute(select(func.coalesce(func.sum(CreditSettlement.amount), 0)).where(CreditSettlement.shift_id == shift_id, CreditSettlement.payment_method == name))).scalar_one() or 0) for name in ("cash", "card", "mobile")}
        cash_expenses = Decimal((await db.execute(select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.shift_id == shift_id, Expense.payment_method == "cash"))).scalar_one() or 0)
        noncash_expenses = Decimal((await db.execute(select(func.coalesce(func.sum(Expense.amount), 0)).where(Expense.shift_id == shift_id, Expense.payment_method.in_(("card", "mobile"))))).scalar_one() or 0)
        cash_received = sum((Decimal(row.total_amount or 0) for row in sales if row.payment_method == "cash" and Decimal(row.total_amount or 0) > 0), Decimal("0")) + settlements["cash"]
        refunds = sum((abs(Decimal(row.total_amount or 0)) for row in sales if row.original_sale_id is not None and Decimal(row.total_amount or 0) < 0), Decimal("0"))
        cash_refunds = sum((abs(Decimal(row.total_amount or 0)) for row in sales if row.original_sale_id is not None and row.payment_method == "cash" and Decimal(row.total_amount or 0) < 0), Decimal("0"))
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
        }

    async def close(self, shift_id, data, actor):
        session = self.require_pos_actor(actor)
        if not data.confirmed:
            raise HTTPException(400, "Shift closure must be confirmed")
        shift = await self.repo.by_id(actor.company_id, shift_id, for_update=True)
        if shift is None:
            raise HTTPException(404, "Shift not found")
        if shift.employee_id != actor.employee.id or shift.device_id != session.device_id:
            raise HTTPException(403, "Only the shift cashier on this register may close the shift")
        if shift.status == "closed":
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
        shift.status = "closed"
        shift.closed_at = datetime.now(timezone.utc)
        shift.closing_note = (data.closing_note or "").strip() or None
        shift.close_idempotency_key = data.idempotency_key.strip()
        self.repo.db.add(AuditEvent(
            company_id=shift.company_id, actor_employee_id=shift.employee_id, device_id=shift.device_id,
            action="cashier_shift_closed", details={"shift_id": str(shift.id), "shift_number": shift.shift_number},
        ))
        await self.repo.db.commit()
        return await self.view(shift, detailed=True)

    @staticmethod
    def _movement_output(movement, actor_name=None):
        return {
            "id": movement.id, "company_id": movement.company_id, "shift_id": movement.shift_id,
            "branch_id": movement.branch_id, "device_id": movement.device_id,
            "employee_id": movement.employee_id, "actor_name": actor_name,
            "movement_type": movement.movement_type, "currency_code": movement.currency_code,
            "amount": movement.amount, "reason": movement.reason,
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
        existing = await self.repo.cash_movement_by_key(actor.company_id, key)
        if existing is not None:
            shift = await self.repo.by_id(actor.company_id, existing.shift_id)
            if shift is not None and self._movement_matches(existing, shift, actor, data):
                return self._movement_output(existing, actor.employee.name)
            raise HTTPException(409, "Cash movement idempotency key is already in use")

        shift = await self.repo.by_id(actor.company_id, shift_id, for_update=True)
        if shift is None:
            raise HTTPException(404, "Shift not found")
        if shift.employee_id != actor.employee.id or shift.device_id != session.device_id or shift.branch_id != session.branch_id:
            raise HTTPException(403, "Only the cashier on this register may record shift cash movements")
        if shift.status != "open":
            raise HTTPException(409, "Cash movements can only be recorded during an open shift")

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

        movement = CashierShiftCashMovement(
            company_id=shift.company_id, shift_id=shift.id, branch_id=shift.branch_id,
            device_id=shift.device_id, employee_id=actor.employee.id,
            movement_type=data.movement_type, currency_code=data.currency_code,
            amount=normalized_amount, reason=data.reason, idempotency_key=key,
        )
        self.repo.db.add(movement)
        self.repo.db.add(AuditEvent(
            company_id=shift.company_id, actor_employee_id=actor.employee.id,
            device_id=shift.device_id, action=f"cashier_shift_{data.movement_type}",
            details={"shift_id": str(shift.id), "movement_id": str(movement.id), "currency_code": data.currency_code, "amount": str(normalized_amount)},
        ))
        try:
            await self.repo.db.commit()
        except IntegrityError as exc:
            await self.repo.db.rollback()
            existing = await self.repo.cash_movement_by_key(actor.company_id, key)
            if existing is not None:
                shift = await self.repo.by_id(actor.company_id, existing.shift_id)
                if shift is not None and self._movement_matches(existing, shift, actor, data):
                    return self._movement_output(existing, actor.employee.name)
            raise HTTPException(409, "Cash movement conflicted with another request") from exc
        await self.repo.db.refresh(movement)
        return self._movement_output(movement, actor.employee.name)

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
