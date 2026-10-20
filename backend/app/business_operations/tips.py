"""Tip receipts/entitlements are not sales, products, payroll or service charges.

Amounts are recorded only after a confirmed transfer. No payment gateway is
invented. All operations serialize on the company, then the processing shift.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_FLOOR
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy import select, func, case
from app.models import (Company, Branch, Employee, Product, BusinessProfile, CommerceOrder, Sale,
    CashierShift, CashierShiftCurrencySnapshot, CashierShiftCashMovement,
    CompanyCurrency, CurrencyExchangeRate, TipSettings, TipEntry, TipEntitlement)
from app.printing.service import PrintingService, permit, digest
from app.financial_access import enforce_actor_branch
from app.shifts.service import ShiftService
from app.shifts.repository import ShiftRepository


def allocate(amount, weights, precision):
    """Deterministic largest-remainder allocation in the currency's minor unit."""
    unit = Decimal(1).scaleb(-precision)
    ticks = int(amount / unit)
    total = sum(weights.values(), Decimal(0))
    if not weights or total <= 0: raise HTTPException(409, "No eligible tip recipients")
    exact = {key: Decimal(ticks) * Decimal(weight) / total for key, weight in weights.items()}
    whole = {key: int(value.to_integral_value(rounding=ROUND_FLOOR)) for key, value in exact.items()}
    remaining = ticks - sum(whole.values())
    for key in sorted(weights, key=lambda key: (-(exact[key] - whole[key]), str(key)))[:remaining]: whole[key] += 1
    return {key: Decimal(value) * unit for key, value in whole.items()}


async def shift_tip_summary(db, shift_id):
    rows = (await db.execute(select(TipEntry.currency_code, TipEntry.payment_method, TipEntry.kind,
        TipEntry.policy, func.sum(TipEntry.amount)).where(TipEntry.shift_id == shift_id)
        .group_by(TipEntry.currency_code, TipEntry.payment_method, TipEntry.kind, TipEntry.policy)
        .order_by(TipEntry.currency_code, TipEntry.payment_method, TipEntry.kind, TipEntry.policy))).all()
    return {"version": 1, "separate_from_product_revenue": True, "totals": [
        {"currency": currency, "method": method, "kind": kind, "policy": policy, "amount": str(amount)}
        for currency, method, kind, policy, amount in rows]}


class TipService(PrintingService):
    async def lock_company(self):
        company = (await self.db.execute(select(Company).where(Company.id == self.actor.company_id).with_for_update())).scalar_one_or_none()
        if not company: raise HTTPException(404, "Company not found")

    async def config(self):
        permit(self.actor, "tips_manage")
        row = await self.db.get(TipSettings, self.actor.company_id)
        profile = await self.db.get(BusinessProfile, self.actor.company_id)
        return {"enabled": bool(row and row.enabled), "policy": row.policy if row else "staff",
            "legacy_queue_review_required": bool(not row and profile and profile.tip_product_id),
            "legacy_queues_reviewed": False,
            "weights": row.weights if row else {}, "business_retention_confirmed": bool(row and row.business_retention_confirmed),
            "service_product_id": row.service_product_id if row else None}

    async def configure(self, data):
        permit(self.actor, "tips_manage"); permit(self.actor, "business_settings_manage")
        await self.lock_company()
        if data.enabled and data.policy == "business" and not data.business_retention_confirmed:
            raise HTTPException(400, "Owner confirmation of permitted business retention is required")
        if data.policy == "shared" and not data.weights: raise HTTPException(400, "Configure eligible employees and positive distribution weights")
        if any(weight < 1 or weight > 10000 for weight in data.weights.values()): raise HTTPException(400, "Distribution weights must be from 1 to 10000")
        # Company-wide policy is owner/administrator only for employee actors.
        if self.actor.employee and self.actor.role not in {"owner", "administrator"}:
            raise HTTPException(403, "Company-wide tip policy requires an owner or administrator")
        for employee_id in data.weights:
            employee = await self.db.get(Employee, employee_id)
            if not employee or employee.company_id != self.actor.company_id or not employee.active or employee.deleted:
                raise HTTPException(400, "An eligible employee is unavailable")
        profile = await self.db.get(BusinessProfile, self.actor.company_id)
        if data.service_product_id:
            product = await self.db.get(Product, data.service_product_id)
            if (not product or product.company_id != self.actor.company_id or product.deleted or not product.active
                    or product.track_inventory or product.product_type not in {"service", "non_stock"}
                    or (profile and profile.tip_product_id == product.id)):
                raise HTTPException(400, "Service charges require a separate active non-stock/service product")
        row = await self.db.get(TipSettings, self.actor.company_id)
        if row is None and profile and profile.tip_product_id and not data.legacy_queues_reviewed:
            raise HTTPException(409, "Review pending legacy tip-product queues on every terminal before enabling the separate tip ledger. No queues were changed")
        if not row: row = TipSettings(company_id=self.actor.company_id); self.db.add(row)
        row.enabled, row.policy = data.enabled, data.policy
        row.weights = {str(key): value for key, value in data.weights.items()}
        row.business_retention_confirmed = data.business_retention_confirmed
        row.service_product_id = data.service_product_id
        # Preserve the existing service-charge calculation and tax path.
        if profile:
            profile.service_product_id = data.service_product_id
        elif data.service_product_id:
            from .profiles import infer_profile
            company = await self.db.get(Company, self.actor.company_id)
            self.db.add(BusinessProfile(company_id=self.actor.company_id, profile=infer_profile(company.business_type), service_product_id=data.service_product_id))
        self.audit("tip_policy_changed", **data.model_dump(mode="json")); await self.db.commit()
        return await self.config()

    async def options(self):
        if self.actor.employee and not any((self.actor.permissions or {}).get(key) for key in ("tips_collect", "tips_manage", "tips_reports_view", "tips_payout")):
            raise HTTPException(403, "Tip access denied")
        branches_query = select(Branch).where(Branch.company_id == self.actor.company_id)
        if self.actor.employee: branches_query = branches_query.where(Branch.id == self.actor.employee.branch_id)
        branches = (await self.db.execute(branches_query)).scalars().all()
        names = {branch.id: branch.name for branch in branches}
        employees = select(Employee).where(Employee.company_id == self.actor.company_id)
        shifts = select(CashierShift).where(CashierShift.company_id == self.actor.company_id, CashierShift.status == "open")
        if self.actor.employee:
            employees = employees.where(Employee.branch_id == self.actor.employee.branch_id)
            shifts = shifts.where(CashierShift.employee_id == self.actor.employee.id,
                CashierShift.device_id == (self.actor.pos_session.device_id if self.actor.pos_session else None))
        return {"branches": [{"id": branch.id, "name": branch.name} for branch in branches],
            "employees": [{"id": employee.id, "name": employee.name, "active": employee.active, "branch_id": employee.branch_id, "branch_name": names.get(employee.branch_id, "Previous branch")}
                for employee in (await self.db.execute(employees.order_by(Employee.name).limit(1000))).scalars()],
            "shifts": [{"id": shift.id, "name": shift.shift_number, "branch_id": shift.branch_id, "device_id": shift.device_id}
                for shift in (await self.db.execute(shifts.limit(100))).scalars()],
            "currencies": [{"code": row.code, "precision": row.decimal_places} for row in (await self.db.execute(select(CompanyCurrency).where(
                CompanyCurrency.company_id == self.actor.company_id, CompanyCurrency.active == True))).scalars()],
            "products": [{"id": product.id, "name": product.name} for product in (await self.db.execute(select(Product).where(
                Product.company_id == self.actor.company_id, Product.active == True, Product.deleted == False,
                Product.track_inventory == False, Product.product_type.in_(["service", "non_stock"])).limit(1000))).scalars()]}

    async def record(self, data):
        if self.actor.employee and (not self.actor.employee.active or self.actor.employee.deleted):
            raise HTTPException(403, "Employee is disabled")
        permit(self.actor, {"collect": "tips_collect", "reverse": "tips_manage", "payout": "tips_payout"}[data.kind])
        if not data.confirmed: raise HTTPException(400, "Confirm the actual tip transfer first")
        await self.lock_company()
        fingerprint = digest({"data": data.model_dump(mode="json"), "actor_type": self.actor.actor_type,
            "actor_id": str(self.actor.employee.id if self.actor.employee else self.actor.user.id)})
        existing = (await self.db.execute(select(TipEntry).where(TipEntry.company_id == self.actor.company_id,
            TipEntry.request_id == data.request_id))).scalar_one_or_none()
        shift = (await self.db.execute(select(CashierShift).where(CashierShift.id == data.shift_id,
            CashierShift.company_id == self.actor.company_id).with_for_update())).scalar_one_or_none()
        if not shift: raise HTTPException(404, "Processing shift not found")
        enforce_actor_branch(self.actor, shift.branch_id)
        if self.actor.employee or data.kind == "collect" or data.payment_method == "cash":
            session = ShiftService.require_pos_actor(self.actor)
            if (shift.employee_id != self.actor.employee.id or shift.device_id != session.device_id
                    or shift.branch_id != session.branch_id or shift.shop_id != session.shop_id):
                raise HTTPException(403, "Use the original cashier's authenticated register")
        if existing:
            if existing.payload_hash != fingerprint: raise HTTPException(409, "Tip request identity already has different values")
            return {"id": existing.id, "already_recorded": True}
        if shift.status != "open": raise HTTPException(409, "Record tips on an open shift; closed snapshots are locked")
        currency = (await self.db.execute(select(CompanyCurrency).where(CompanyCurrency.company_id == self.actor.company_id,
            CompanyCurrency.code == data.currency_code, CompanyCurrency.active == True))).scalar_one_or_none()
        if not currency or not getattr(currency, data.payment_method + "_accepted"):
            raise HTTPException(400, "Currency/payment method not enabled")
        precision = currency.decimal_places
        if data.amount != data.amount.quantize(Decimal(1).scaleb(-precision)):
            raise HTTPException(400, "Tip amount exceeds the currency precision")
        entitlements = {}; sale_id = None; original = None
        if data.kind == "collect":
            if not data.sale_id or data.original_id or data.employee_id: raise HTTPException(400, "A collection requires its original sale, not an arbitrary employee")
            settings = await self.db.get(TipSettings, self.actor.company_id)
            if not settings or not settings.enabled: raise HTTPException(409, "Enable a reviewed tip policy first")
            sale = await self.db.get(Sale, data.sale_id)
            if (not sale or sale.company_id != self.actor.company_id or sale.branch_id != shift.branch_id
                    or sale.device_id != shift.device_id or sale.original_sale_id or sale.total_amount <= 0):
                raise HTTPException(404, "Original completed sale is not on this register")
            sale_id, policy = sale.id, settings.policy
            order = (await self.db.execute(select(CommerceOrder).where(CommerceOrder.sale_id == sale.id))).scalar_one_or_none()
            employee_id = order.waiter_id if order and order.waiter_id else sale.employee_id
            if policy == "staff":
                employee = await self.db.get(Employee, employee_id) if employee_id else None
                if not employee or employee.company_id != shift.company_id:
                    raise HTTPException(409, "Original serving employee needs review")
                entitlements = {employee.id: data.amount}
            elif policy == "shared":
                eligible = (await self.db.execute(select(Employee).where(Employee.company_id == shift.company_id,
                    Employee.branch_id == shift.branch_id, Employee.active == True, Employee.deleted == False))).scalars().all()
                weights = {employee.id: Decimal(settings.weights[str(employee.id)]) for employee in eligible if str(employee.id) in settings.weights}
                entitlements = allocate(data.amount, weights, precision)
            elif not settings.business_retention_confirmed:
                raise HTTPException(409, "Business retention must be confirmed")
        elif data.kind == "reverse":
            if not data.original_id or data.sale_id or data.employee_id: raise HTTPException(400, "Choose the original tip receipt")
            original = await self.db.get(TipEntry, data.original_id)
            if not original or original.company_id != shift.company_id or original.branch_id != shift.branch_id or original.kind != "collect":
                raise HTTPException(404, "Original tip not found in this branch")
            if original.payment_method != data.payment_method or original.currency_code != data.currency_code:
                raise HTTPException(409, "Refund tips in the original currency and payment method")
            refunded = (await self.db.execute(select(func.coalesce(func.sum(TipEntry.amount), 0)).where(TipEntry.original_id == original.id))).scalar_one()
            if data.amount > original.amount - refunded: raise HTTPException(409, "Tip reversal exceeds the remaining original tip")
            sale_id, policy = original.sale_id, original.policy
            originals = (await self.db.execute(select(TipEntitlement).where(TipEntitlement.entry_id == original.id))).scalars().all()
            weights = {}
            for allocation in originals:
                reversed_amount = (await self.db.execute(select(func.coalesce(func.sum(TipEntitlement.amount),0)).join(TipEntry,
                    TipEntry.id == TipEntitlement.entry_id).where(TipEntry.original_id == original.id,
                    TipEntitlement.employee_id == allocation.employee_id))).scalar_one()
                remaining = allocation.amount + reversed_amount
                if remaining > 0: weights[allocation.employee_id] = remaining
            if weights: entitlements = {key: -value for key, value in allocate(data.amount, weights, precision).items()}
        else:
            if not data.employee_id or data.sale_id or data.original_id: raise HTTPException(400, "Choose the employee receiving this payout")
            employee = await self.db.get(Employee, data.employee_id)
            if not employee or employee.company_id != shift.company_id:
                raise HTTPException(404, "Employee not found in this branch")
            balance = (await self.db.execute(select(func.coalesce(func.sum(TipEntitlement.amount),0)).join(TipEntry,
                TipEntry.id == TipEntitlement.entry_id).where(TipEntry.company_id == shift.company_id,
                TipEntry.branch_id == shift.branch_id, TipEntry.currency_code == data.currency_code,
                TipEntitlement.employee_id == employee.id))).scalar_one()
            if data.amount > balance: raise HTTPException(409, "Payout exceeds the employee's outstanding tip entitlement")
            entitlements, policy = {employee.id: -data.amount}, "staff"
        try:
            movement = None
            if data.payment_method == "cash":
                snapshot = (await self.db.execute(select(CashierShiftCurrencySnapshot).where(
                    CashierShiftCurrencySnapshot.shift_id == shift.id, CashierShiftCurrencySnapshot.currency_code == data.currency_code))).scalar_one_or_none()
                if not snapshot or not snapshot.cash_accepted_snapshot: raise HTTPException(409, "Cash currency is not enabled on this shift")
                if data.kind != "collect":
                    sales, refunds, settlements, expenses, cash_in, cash_out = await ShiftService(ShiftRepository(self.db))._currency_activity(shift.id, data.currency_code)
                    if data.amount > snapshot.opening_float + sales + settlements + cash_in - refunds - expenses - cash_out:
                        raise HTTPException(409, "Tip refund/payout exceeds the drawer cash balance")
                rate = Decimal(1) if currency.is_base else (await self.db.execute(select(CurrencyExchangeRate.foreign_units_per_base).where(
                    CurrencyExchangeRate.company_id == shift.company_id, CurrencyExchangeRate.currency_id == currency.id,
                    CurrencyExchangeRate.effective_at <= datetime.now(timezone.utc)).order_by(CurrencyExchangeRate.effective_at.desc(), CurrencyExchangeRate.created_at.desc()).limit(1))).scalar_one_or_none()
                if not rate: raise HTTPException(409, "No authorized exchange rate is available")
                movement = CashierShiftCashMovement(company_id=shift.company_id, shift_id=shift.id, branch_id=shift.branch_id,
                    device_id=shift.device_id, employee_id=shift.employee_id, movement_type="cash_in" if data.kind == "collect" else "cash_out",
                    currency_code=data.currency_code, amount=data.amount, base_amount=(data.amount / rate).quantize(Decimal("0.01")),
                    exchange_rate_snapshot=rate, reason=f"Tip {data.kind}: {data.reason}", idempotency_key=f"tip:{data.request_id}")
                self.db.add(movement); await self.db.flush()
            entry = TipEntry(company_id=shift.company_id, branch_id=shift.branch_id, shift_id=shift.id, sale_id=sale_id,
                original_id=original.id if original else None, request_id=data.request_id, payload_hash=fingerprint,
                kind=data.kind, policy=policy, payment_method=data.payment_method, currency_code=data.currency_code,
                decimal_places=precision, amount=data.amount, reason=data.reason, reference=data.reference,
                cash_movement_id=movement.id if movement else None)
            self.db.add(entry); await self.db.flush()
            for employee_id, amount in entitlements.items():
                if amount: self.db.add(TipEntitlement(entry_id=entry.id, employee_id=employee_id, amount=amount))
            self.audit("tip_" + data.kind, tip_id=entry.id, **data.model_dump(mode="json"), policy=policy,
                allocations={str(key): str(value) for key, value in entitlements.items()})
            await self.db.commit()
            return {"id": entry.id, "already_recorded": False}
        except Exception:
            await self.db.rollback(); raise

    async def report(self, start, end, branch_id=None):
        permit(self.actor, "tips_reports_view")
        if end < start or (end-start).days > 366: raise HTTPException(400, "Choose a date range of at most 366 days")
        if self.actor.employee:
            branch_id = branch_id or self.actor.employee.branch_id; enforce_actor_branch(self.actor, branch_id)
        scope = [TipEntry.company_id == self.actor.company_id]
        if branch_id: scope.append(TipEntry.branch_id == branch_id)
        dated = [*scope, TipEntry.created_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
            TipEntry.created_at < datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)]
        totals = (await self.db.execute(select(TipEntry.currency_code, TipEntry.payment_method, TipEntry.kind, TipEntry.policy,
            func.sum(TipEntry.amount)).where(*dated).group_by(TipEntry.currency_code, TipEntry.payment_method, TipEntry.kind, TipEntry.policy))).all()
        net_receipts = (await self.db.execute(select(TipEntry.currency_code, TipEntry.payment_method, TipEntry.policy,
            func.sum(case((TipEntry.kind == "collect", TipEntry.amount), (TipEntry.kind == "reverse", -TipEntry.amount), else_=0)))
            .where(*dated).group_by(TipEntry.currency_code, TipEntry.payment_method, TipEntry.policy))).all()
        balances = (await self.db.execute(select(TipEntitlement.employee_id, Employee.name, TipEntry.branch_id, Branch.name,
            TipEntry.currency_code, func.sum(TipEntitlement.amount)).join(TipEntry, TipEntry.id == TipEntitlement.entry_id)
            .join(Employee, Employee.id == TipEntitlement.employee_id).join(Branch, Branch.id == TipEntry.branch_id).where(*scope)
            .group_by(TipEntitlement.employee_id, Employee.name, TipEntry.branch_id, Branch.name, TipEntry.currency_code))).all()
        entries = (await self.db.execute(select(TipEntry).where(*dated).order_by(TipEntry.created_at.desc()).limit(1000))).scalars().all()
        return {"dates_timezone": "UTC", "balances_all_time": True,
            "net_tip_receipts": [{"currency": c, "method": m, "policy": p, "amount": str(a)} for c,m,p,a in net_receipts],
            "totals": [{"currency": c, "method": m, "kind": k, "policy": p, "amount": str(a)} for c,m,k,p,a in totals],
            "balances": [{"employee_id": employee, "employee": name, "branch_id": branch, "branch_name": branch_name, "currency": c, "outstanding": str(a), "overpaid_after_reversal": a < 0} for employee,name,branch,branch_name,c,a in balances],
            "entries": [{"id": row.id, "kind": row.kind, "policy": row.policy, "method": row.payment_method,
                "currency": row.currency_code, "amount": str(row.amount), "sale_id": row.sale_id,
                "shift_id": row.shift_id, "reference": row.reference, "created_at": row.created_at} for row in entries]}
