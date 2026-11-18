import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from app.printing.service import permit
from app import financial_commands
from app.subscriptions.write_policy import require_new_write

from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
from app.financial_access import enforce_actor_branch, enforce_actor_company
from app.models import AuditEvent, CreditSettlement
from app.currencies.repository import CurrencyRepository
from app.currencies.service import CurrencyService
from app.financial_context import resolve_shift_for_write


class CreditService:
    def __init__(self, repo: CreditRepository):
        self.repo = repo

    @staticmethod
    def settlement_view(settlement, outstanding=None, actor_id=None, actor_name="Unknown"):
        values = {column.name: getattr(settlement, column.name) for column in settlement.__table__.columns}
        values["outstanding_balance"] = outstanding
        values["actor_id"] = actor_id
        values["actor_name"] = actor_name
        return values

    @staticmethod
    def validate_currency_quote(data, snapshot, current_version):
        if data.currency_config_version is not None and current_version is not None and current_version != data.currency_config_version:
            raise HTTPException(409, "Payment currency configuration changed. Refresh the settlement quote and try again.")
        if data.exchange_rate_id is not None and data.exchange_rate_id != snapshot["exchange_rate_id"]:
            raise HTTPException(409, "Exchange rate changed. Refresh the settlement quote and try again.")
        if data.exchange_rate_snapshot is not None and Decimal(data.exchange_rate_snapshot) != Decimal(snapshot["exchange_rate_snapshot"]):
            raise HTTPException(409, "Exchange rate snapshot changed. Refresh the settlement quote and try again.")

    @staticmethod
    def ensure_same_request(existing, data):
        requested_amount = data.amount
        if (
            existing.receivable_id != data.receivable_id
            or existing.branch_id != data.branch_id
            or (requested_amount is not None and Decimal(existing.amount) != Decimal(requested_amount))
            or (data.original_amount is not None and Decimal(existing.original_amount or 0) != Decimal(data.original_amount))
            or (data.tendered_amount_original is not None and Decimal(existing.tendered_amount_original or existing.original_amount or 0) != Decimal(data.tendered_amount_original))
            or (data.payment_currency_code is not None and existing.payment_currency_code != data.payment_currency_code.strip().upper())
            or (data.exchange_rate_id is not None and existing.exchange_rate_id != data.exchange_rate_id)
            or (data.shift_id is not None and existing.shift_id != data.shift_id)
            or existing.payment_method != data.payment_method
        ):
            raise HTTPException(409, "Idempotency key was already used for a different settlement")

    async def list_receivables(self, company_id, actor, **filters):
        enforce_actor_company(actor, company_id)
        branch_id = filters.get("branch_id")
        if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            if branch_id is not None:
                enforce_actor_branch(actor, branch_id)
            filters["branch_id"] = actor.employee.branch_id
        rows = await self.repo.list_receivables(company_id, **filters)
        total = None
        if filters.get("with_total"):
            rows, total = rows
        items = [{**{column.name: getattr(receivable, column.name) for column in receivable.__table__.columns}, "customer_name": name, "customer_code": code, "sale_receipt_number": receipt} for receivable, name, code, receipt in rows]
        return (items, total) if total is not None else items

    async def get_receivable(self, company_id, receivable_id, actor):
        enforce_actor_company(actor, company_id)
        receivable = await self.repo.get_receivable(company_id, receivable_id)
        if not receivable:
            raise HTTPException(404, "Receivable not found")
        enforce_actor_branch(actor, receivable.branch_id)
        return receivable

    async def create_settlement(self, data: SettlementCreate, actor):
        permit(actor, "credit_settlements")
        enforce_actor_company(actor, data.company_id)
        enforce_actor_branch(actor, data.branch_id)
        data = data.model_copy()
        command_hash = await financial_commands.lock_command(self.repo.db, "credit", data, actor)
        existing = await self.repo.get_settlement_by_key(data.company_id, data.idempotency_key)
        if existing:
            await financial_commands.verify_replay(self.repo.db, existing, data, actor, command_hash)
            receivable = await self.repo.get_receivable(data.company_id, existing.receivable_id)
            actor_id, actor_name = await self.repo.actor_identity(data.company_id, existing.cashier_employee_id, existing.actor_user_id)
            return self.settlement_view(existing, receivable.outstanding_balance if receivable else None, actor_id, actor_name)
        await require_new_write(self.repo.db, data.company_id)

        branch = await self.repo.get_branch(data.company_id, data.branch_id)
        if not branch:
            raise HTTPException(404, "Branch not found")
        shift = await resolve_shift_for_write(
            self.repo.db, actor, data.company_id, branch.id, data.shift_id,
            attach_active=True,
        )
        receivable = await self.repo.get_receivable(data.company_id, data.receivable_id, for_update=True)
        if not receivable:
            raise HTTPException(404, "Receivable not found")
        enforce_actor_branch(actor, receivable.branch_id)
        outstanding = Decimal(receivable.outstanding_balance)
        currency_repository = CurrencyRepository(self.repo.db)
        currency_service = CurrencyService(currency_repository)
        settings = await currency_repository.settings(data.company_id, for_update=True)
        current_version = int(getattr(settings, "currency_config_version", 0) or 0) if settings is not None else None
        if data.settle_full:
            snapshot = await currency_service.resolve_from_base(
                data.company_id, data.payment_method, data.payment_currency_code,
                outstanding, at=datetime.now(timezone.utc),
            )
            amount = outstanding
        else:
            original_input = data.original_amount if data.original_amount is not None else data.amount
            if original_input is None:
                raise HTTPException(400, "Settlement amount is required")
            snapshot = await currency_service.resolve_snapshot(
                data.company_id, data.payment_method, data.payment_currency_code,
                original_input, at=datetime.now(timezone.utc),
            )
            amount = Decimal(snapshot["base_amount"]).quantize(Decimal("0.01"))
            if data.amount is not None and data.original_amount is not None and Decimal(data.amount).quantize(Decimal("0.01")) != amount:
                raise HTTPException(409, "Settlement base amount does not match the authoritative currency conversion")
        self.validate_currency_quote(data, snapshot, current_version)
        if amount <= 0:
            raise HTTPException(400, "Settlement amount must be greater than zero")
        if amount > outstanding:
            raise HTTPException(409, "Settlement exceeds the outstanding balance")

        payment_places = int(snapshot["currency"].decimal_places)
        payment_quantum = Decimal(1).scaleb(-payment_places)
        applied_original = Decimal(snapshot["original_amount"]).quantize(payment_quantum)
        if not data.settle_full and Decimal(data.original_amount if data.original_amount is not None else data.amount) != applied_original:
            raise HTTPException(400, "Settlement amount exceeds the selected currency precision")
        if data.payment_method == "cash":
            raw_tendered = Decimal(data.tendered_amount_original or applied_original)
            tendered_original = raw_tendered.quantize(payment_quantum)
            if raw_tendered != tendered_original:
                raise HTTPException(400, "Tendered amount exceeds the selected currency precision")
            if tendered_original < applied_original:
                raise HTTPException(400, "Tendered amount is less than the settlement amount")
            change_original = (tendered_original - applied_original).quantize(payment_quantum)
        else:
            if data.tendered_amount_original is not None and Decimal(data.tendered_amount_original).quantize(payment_quantum) != applied_original:
                raise HTTPException(400, "Tendered amount must equal the settlement amount for non-cash payments")
            tendered_original = applied_original
            change_original = Decimal("0").quantize(payment_quantum)

        new_outstanding = (outstanding - amount).quantize(Decimal("0.01"))
        receivable.amount_settled = (Decimal(receivable.amount_settled) + amount).quantize(Decimal("0.01"))
        receivable.outstanding_balance = new_outstanding
        receivable.status = "paid" if new_outstanding == 0 else "partially_paid"
        settlement_id = uuid.uuid4()
        received_at = data.received_at or datetime.now(timezone.utc)
        if received_at.tzinfo is None or received_at.utcoffset() is None:
            raise HTTPException(400, "received_at must include a timezone")
        settlement = CreditSettlement(
            id=settlement_id, company_id=data.company_id, receivable_id=receivable.id,
            customer_id=receivable.customer_id, shop_id=branch.shop_id, branch_id=branch.id,
            actor_user_id=actor.user.id if actor.actor_type == "user" else None,
            cashier_employee_id=actor.employee.id if actor.actor_type == "employee" else None,
            device_id=shift.device_id if shift else (actor.pos_session.device_id if actor.actor_type == "employee" and actor.pos_session else None),
            shift_id=shift.id if shift else None,
            base_currency_code=snapshot["base_currency"].code,
            payment_currency_code=snapshot["currency"].code,
            exchange_rate_id=snapshot["exchange_rate_id"],
            exchange_rate_snapshot=snapshot["exchange_rate_snapshot"],
            original_amount=snapshot["original_amount"],
            tendered_amount_original=tendered_original,
            change_amount_original=change_original,
            amount=amount, payment_method=data.payment_method,
            reference=(data.reference or "").strip() or None, note=(data.note or "").strip() or None,
            received_at=received_at,
            idempotency_key=data.idempotency_key.strip(),
            receipt_number=f"CST-{datetime.now(timezone.utc):%Y%m%d}-{str(settlement_id)[:8].upper()}",
        )
        audit = AuditEvent(
            company_id=data.company_id, actor_user_id=settlement.actor_user_id,
            actor_employee_id=settlement.cashier_employee_id, action="credit_settlement_posted",
            device_id=settlement.device_id,
            details={"settlement_id": str(settlement.id), "receivable_id": str(receivable.id), "amount": str(amount), "original_amount": str(settlement.original_amount), "tendered_amount_original": str(settlement.tendered_amount_original), "change_amount_original": str(settlement.change_amount_original), "currency": settlement.payment_currency_code, "rate": str(settlement.exchange_rate_snapshot), "payment_method": data.payment_method, "shift_id": str(settlement.shift_id) if settlement.shift_id else None},
        )
        await financial_commands.stamp(self.repo.db, settlement, actor, command_hash)
        saved = await self.repo.save_settlement(receivable, settlement, audit)
        actor_id, actor_name = await self.repo.actor_identity(data.company_id, saved.cashier_employee_id, saved.actor_user_id)
        return self.settlement_view(saved, new_outstanding, actor_id, actor_name)

    async def list_settlements(self, company_id, actor, **filters):
        enforce_actor_company(actor, company_id)
        branch_id = filters.get("branch_id")
        if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            if branch_id is not None:
                enforce_actor_branch(actor, branch_id)
            filters["branch_id"] = actor.employee.branch_id
        rows = await self.repo.list_settlements(company_id, **filters)
        total = None
        if filters.get("with_total"):
            rows, total = rows
        items = [self.settlement_view(settlement, actor_id=actor_id, actor_name=actor_name) | {"customer_name": customer_name, "customer_code": customer_code, "sale_receipt_number": sale_receipt_number} for settlement, actor_id, actor_name, customer_name, customer_code, sale_receipt_number in rows]
        return (items, total) if total is not None else items
