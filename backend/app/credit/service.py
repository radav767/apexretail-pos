import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from app.credit.repository import CreditRepository
from app.credit.schema import SettlementCreate
from app.financial_access import enforce_actor_branch, enforce_actor_company
from app.models import AuditEvent, CreditSettlement


class CreditService:
    def __init__(self, repo: CreditRepository):
        self.repo = repo

    @staticmethod
    def settlement_view(settlement, outstanding=None):
        values = {column.name: getattr(settlement, column.name) for column in settlement.__table__.columns}
        values["outstanding_balance"] = outstanding
        return values

    @staticmethod
    def ensure_same_request(existing, data):
        if (
            existing.receivable_id != data.receivable_id
            or existing.branch_id != data.branch_id
            or Decimal(existing.amount) != Decimal(data.amount)
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
        return [{**{column.name: getattr(receivable, column.name) for column in receivable.__table__.columns}, "customer_name": name, "customer_code": code, "sale_receipt_number": receipt} for receivable, name, code, receipt in rows]

    async def get_receivable(self, company_id, receivable_id, actor):
        enforce_actor_company(actor, company_id)
        receivable = await self.repo.get_receivable(company_id, receivable_id)
        if not receivable:
            raise HTTPException(404, "Receivable not found")
        enforce_actor_branch(actor, receivable.branch_id)
        return receivable

    async def create_settlement(self, data: SettlementCreate, actor):
        enforce_actor_company(actor, data.company_id)
        enforce_actor_branch(actor, data.branch_id)
        existing = await self.repo.get_settlement_by_key(data.company_id, data.idempotency_key)
        if existing:
            self.ensure_same_request(existing, data)
            receivable = await self.repo.get_receivable(data.company_id, existing.receivable_id)
            return self.settlement_view(existing, receivable.outstanding_balance if receivable else None)

        branch = await self.repo.get_branch(data.company_id, data.branch_id)
        if not branch:
            raise HTTPException(404, "Branch not found")
        receivable = await self.repo.get_receivable(data.company_id, data.receivable_id, for_update=True)
        if not receivable:
            raise HTTPException(404, "Receivable not found")
        enforce_actor_branch(actor, receivable.branch_id)
        existing = await self.repo.get_settlement_by_key(data.company_id, data.idempotency_key)
        if existing:
            self.ensure_same_request(existing, data)
            return self.settlement_view(existing, receivable.outstanding_balance)
        amount = Decimal(data.amount).quantize(Decimal("0.01"))
        outstanding = Decimal(receivable.outstanding_balance)
        if amount <= 0:
            raise HTTPException(400, "Settlement amount must be greater than zero")
        if amount > outstanding:
            raise HTTPException(409, "Settlement exceeds the outstanding balance")

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
            device_id=None, amount=amount, payment_method=data.payment_method,
            reference=(data.reference or "").strip() or None, note=(data.note or "").strip() or None,
            received_at=received_at,
            idempotency_key=data.idempotency_key.strip(),
            receipt_number=f"CST-{datetime.now(timezone.utc):%Y%m%d}-{str(settlement_id)[:8].upper()}",
        )
        audit = AuditEvent(
            company_id=data.company_id, actor_user_id=settlement.actor_user_id,
            actor_employee_id=settlement.cashier_employee_id, action="credit_settlement_posted",
            details={"settlement_id": str(settlement.id), "receivable_id": str(receivable.id), "amount": str(amount), "payment_method": data.payment_method},
        )
        saved = await self.repo.save_settlement(receivable, settlement, audit)
        return self.settlement_view(saved, new_outstanding)

    async def list_settlements(self, company_id, actor, **filters):
        enforce_actor_company(actor, company_id)
        branch_id = filters.get("branch_id")
        if actor.actor_type == "employee" and actor.role not in {"owner", "administrator"}:
            if branch_id is not None:
                enforce_actor_branch(actor, branch_id)
            filters["branch_id"] = actor.employee.branch_id
        return await self.repo.list_settlements(company_id, **filters)
