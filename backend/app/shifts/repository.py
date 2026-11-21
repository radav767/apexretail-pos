from sqlalchemy import and_, func, select

from app.models import (
    Branch, CashierShift, CashierShiftCashMovement, CashierShiftCurrencySnapshot,
    CompanyCurrency, CompanySetting, CreditSettlement, Device, Employee, Sale, Shop,
    OfflineSaleResolution,SaleTender,
)


class ShiftRepository:
    async def tip_summary(self, shift_id):
        from app.business_operations.tips import shift_tip_summary
        return await shift_tip_summary(self.db, shift_id)

    def __init__(self, db):
        self.db = db

    async def begin_command(self, data, actor, kind, shift=None):
        from .commands import begin
        return await begin(self.db, data, actor, kind, shift)

    def record_command(self, proof, shift_id, *, movement_id=None, resolution_id=None, stage=True):
        from .commands import receipt
        result = receipt(proof, shift_id, movement_id=movement_id, resolution_id=resolution_id)
        if stage: self.db.add(result)
        return result

    async def current(self, employee_id, device_id, *, company_id=None, for_update=False):
        query = select(CashierShift).where(
            CashierShift.employee_id == employee_id,
            CashierShift.device_id == device_id,
            CashierShift.status == "open",
        )
        if company_id is not None:
            query = query.where(CashierShift.company_id == company_id)
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def by_id(self, company_id, shift_id, *, for_update=False):
        query = select(CashierShift).where(
            CashierShift.company_id == company_id,
            CashierShift.id == shift_id,
        )
        if for_update:
            query = query.with_for_update()
        return (await self.db.execute(query)).scalar_one_or_none()

    async def by_open_key(self, company_id, key):
        return (await self.db.execute(select(CashierShift).where(
            CashierShift.company_id == company_id,
            CashierShift.open_idempotency_key == key,
        ))).scalar_one_or_none()

    async def active_currencies(self, company_id):
        return list((await self.db.execute(select(CompanyCurrency).where(
            CompanyCurrency.company_id == company_id,
            CompanyCurrency.active.is_(True),
        ).order_by(CompanyCurrency.display_order, CompanyCurrency.code))).scalars())

    async def snapshots(self, shift_id, *, for_update=False):
        query = select(CashierShiftCurrencySnapshot).where(
            CashierShiftCurrencySnapshot.shift_id == shift_id
        ).order_by(CashierShiftCurrencySnapshot.currency_code)
        if for_update:
            query = query.with_for_update()
        return list((await self.db.execute(query)).scalars())

    async def cash_movement_by_key(self, company_id, key):
        return (await self.db.execute(select(CashierShiftCashMovement).where(
            CashierShiftCashMovement.company_id == company_id,
            CashierShiftCashMovement.idempotency_key == key,
        ))).scalar_one_or_none()

    async def cash_movement_totals(self, shift_id, currency_code):
        rows = (await self.db.execute(select(
            CashierShiftCashMovement.movement_type,
            func.coalesce(func.sum(CashierShiftCashMovement.amount), 0),
        ).where(
            CashierShiftCashMovement.shift_id == shift_id,
            CashierShiftCashMovement.currency_code == currency_code,
        ).group_by(CashierShiftCashMovement.movement_type))).all()
        totals = {"cash_in": 0, "cash_out": 0}
        for movement_type, amount in rows:
            totals[movement_type] = amount
        return totals

    async def cash_movements(self, shift_id):
        rows = (await self.db.execute(
            select(CashierShiftCashMovement, Employee.name.label("actor_name"))
            .outerjoin(Employee, and_(
                Employee.id == CashierShiftCashMovement.employee_id,
                Employee.company_id == CashierShiftCashMovement.company_id,
            ))
            .where(CashierShiftCashMovement.shift_id == shift_id)
            .order_by(CashierShiftCashMovement.created_at.desc(), CashierShiftCashMovement.id.desc())
        )).all()
        return [
            {column.name: getattr(movement, column.name) for column in movement.__table__.columns}
            | {"actor_name": actor_name}
            for movement, actor_name in rows
        ]

    async def offline_resolution(self, company_id, *, client_sale_id=None, idempotency_key=None):
        query = select(OfflineSaleResolution).where(OfflineSaleResolution.company_id == company_id)
        if client_sale_id is not None:
            query = query.where(OfflineSaleResolution.client_sale_id == client_sale_id)
        elif idempotency_key is not None:
            query = query.where(OfflineSaleResolution.idempotency_key == idempotency_key)
        else:
            return None
        return (await self.db.execute(query)).scalar_one_or_none()

    async def offline_resolutions(self, company_id, *, action=None, shift_id=None, limit=25, offset=0):
        query = select(OfflineSaleResolution).where(OfflineSaleResolution.company_id == company_id)
        if action is not None:
            query = query.where(OfflineSaleResolution.action == action)
        if shift_id is not None:
            query = query.where(OfflineSaleResolution.original_shift_id == shift_id)
        total = int((await self.db.execute(select(func.count()).select_from(query.subquery()))).scalar_one())
        rows = list((await self.db.execute(
            query.order_by(OfflineSaleResolution.created_at.desc()).limit(limit).offset(offset)
        )).scalars())
        return rows, total

    async def list(self, company_id, *, shop_id=None, branch_id=None, employee_id=None, device_id=None, status=None, start_at=None, end_at=None, limit=25, offset=0):
        query = self.filtered_query(
            company_id, shop_id=shop_id, branch_id=branch_id, employee_id=employee_id,
            device_id=device_id, status=status, start_at=start_at, end_at=end_at,
        )
        total = int((await self.db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one())
        rows = list((await self.db.execute(query.order_by(CashierShift.opened_at.desc(), CashierShift.id.desc()).limit(limit).offset(offset))).scalars())
        return rows, total

    @staticmethod
    def filtered_query(company_id, *, shop_id=None, branch_id=None, employee_id=None, device_id=None, status=None, start_at=None, end_at=None):
        query = select(CashierShift).where(CashierShift.company_id == company_id)
        for value, column in (
            (shop_id, CashierShift.shop_id), (branch_id, CashierShift.branch_id), (employee_id, CashierShift.employee_id),
            (device_id, CashierShift.device_id), (status, CashierShift.status),
        ):
            if value is not None:
                query = query.where(column == value)
        if start_at is not None:
            query = query.where(CashierShift.opened_at >= start_at)
        if end_at is not None:
            query = query.where(CashierShift.opened_at < end_at)
        return query

    async def identity(self, shift):
        values = await self.identities([shift])
        return values.get(shift.id, {})

    async def identities(self, shifts):
        if not shifts:
            return {}
        company_id = shifts[0].company_id
        shift_ids = [row.id for row in shifts]
        row = (await self.db.execute(
            select(
                CashierShift.id.label("shift_id"),
                Employee.name.label("cashier_name"),
                Employee.role.label("cashier_role"),
                Branch.name.label("branch_name"),
                Shop.name.label("shop_name"),
                Device.friendly_name.label("device_friendly_name"),
                Device.name.label("device_name"),
                Device.pos_number.label("pos_number"),
            )
            .select_from(CashierShift)
            .outerjoin(Employee, and_(
                Employee.id == CashierShift.employee_id,
                Employee.company_id == CashierShift.company_id,
            ))
            .outerjoin(Branch, and_(
                Branch.id == CashierShift.branch_id,
                Branch.company_id == CashierShift.company_id,
            ))
            .outerjoin(Shop, and_(
                Shop.id == CashierShift.shop_id,
                Shop.company_id == CashierShift.company_id,
            ))
            .outerjoin(Device, and_(
                Device.id == CashierShift.device_id,
                Device.company_id == CashierShift.company_id,
            ))
            .where(CashierShift.company_id == company_id, CashierShift.id.in_(shift_ids))
        )).mappings().all()
        result = {}
        for identity in row:
            device_name = identity["device_friendly_name"] or identity["device_name"]
            if not device_name and identity["pos_number"] is not None:
                device_name = f"Register {identity['pos_number']}"
            result[identity["shift_id"]] = {
                "cashier_name": identity["cashier_name"],
                "cashier_role": identity["cashier_role"],
                "branch_name": identity["branch_name"],
                "shop_name": identity["shop_name"],
                "register_name": device_name,
            }
        return result

    async def filter_options(self, company_id, *, branch_id=None):
        shift_filters = [CashierShift.company_id == company_id]
        if branch_id is not None:
            shift_filters.append(CashierShift.branch_id == branch_id)
        employee_ids = select(CashierShift.employee_id).where(*shift_filters)
        branch_ids = select(CashierShift.branch_id).where(*shift_filters)
        device_ids = select(CashierShift.device_id).where(*shift_filters)

        employees = (await self.db.execute(
            select(Employee.id, Employee.name, Employee.role)
            .where(
                Employee.company_id == company_id,
                Employee.id.in_(employee_ids),
            )
            .order_by(Employee.name, Employee.id)
        )).all()
        branches = (await self.db.execute(
            select(Branch.id, Branch.name, Shop.name.label("shop_name"))
            .join(Shop, and_(Shop.id == Branch.shop_id, Shop.company_id == Branch.company_id))
            .where(
                Branch.company_id == company_id,
                Branch.id.in_(branch_ids),
            )
            .order_by(Shop.name, Branch.name, Branch.id)
        )).all()
        devices = (await self.db.execute(
            select(Device.id, Device.name, Device.friendly_name, Device.pos_number)
            .where(
                Device.company_id == company_id,
                Device.id.in_(device_ids),
            )
            .order_by(Device.friendly_name, Device.name, Device.id)
        )).all()
        return {
            "cashiers": [{"id": row.id, "name": row.name, "role": row.role} for row in employees],
            "branches": [{"id": row.id, "name": row.name, "shop_name": row.shop_name} for row in branches],
            "devices": [{
                "id": row.id,
                "name": row.friendly_name or row.name or (f"Register {row.pos_number}" if row.pos_number is not None else "Register"),
            } for row in devices],
        }

    async def report_summary(self, company_id, *, shop_id=None, branch_id=None, employee_id=None, device_id=None, status=None, start_at=None, end_at=None):
        filtered = self.filtered_query(
            company_id, shop_id=shop_id, branch_id=branch_id, employee_id=employee_id,
            device_id=device_id, status=status, start_at=start_at, end_at=end_at,
        )
        filtered_rows = filtered.with_only_columns(CashierShift.id, CashierShift.status).order_by(None).subquery()
        shift_ids = select(filtered_rows.c.id)
        counts = (await self.db.execute(select(
            func.count(filtered_rows.c.id),
            func.count(filtered_rows.c.id).filter(filtered_rows.c.status == "open"),
            func.count(filtered_rows.c.id).filter(filtered_rows.c.status == "closed"),
        ))).one()
        total_sales = (await self.db.execute(select(
            func.coalesce(func.sum(Sale.total_amount), 0)
        ).where(Sale.shift_id.in_(shift_ids)))).scalar_one()
        positive_cash_sales = (await self.db.execute(select(
            func.coalesce(func.sum(Sale.total_amount), 0)
        ).where(
            Sale.shift_id.in_(shift_ids), Sale.payment_method == "cash", Sale.total_amount > 0,
        ))).scalar_one()
        split_cash=(await self.db.execute(select(func.coalesce(func.sum(SaleTender.applied_base),0)).join(Sale,Sale.id==SaleTender.sale_id).where(Sale.shift_id.in_(shift_ids),SaleTender.company_id==company_id,Sale.payment_method=='split',SaleTender.method=='cash'))).scalar_one()
        cash_settlements = (await self.db.execute(select(
            func.coalesce(func.sum(CreditSettlement.amount), 0)
        ).where(
            CreditSettlement.shift_id.in_(shift_ids), CreditSettlement.payment_method == "cash",
        ))).scalar_one()
        variance_rows = (await self.db.execute(
            select(
                CashierShiftCurrencySnapshot.currency_code,
                func.coalesce(func.sum(CashierShiftCurrencySnapshot.variance), 0),
            )
            .join(CashierShift, CashierShift.id == CashierShiftCurrencySnapshot.shift_id)
            .where(
                CashierShift.id.in_(shift_ids),
                CashierShiftCurrencySnapshot.variance.is_not(None),
            )
            .group_by(CashierShiftCurrencySnapshot.currency_code)
            .order_by(CashierShiftCurrencySnapshot.currency_code)
        )).all()
        base_currency_code = (await self.db.execute(
            select(CompanyCurrency.code)
            .join(CompanySetting, CompanySetting.base_currency_id == CompanyCurrency.id)
            .where(CompanySetting.company_id == company_id, CompanyCurrency.company_id == company_id)
        )).scalar_one_or_none()
        return {
            "total_shifts": int(counts[0] or 0),
            "open_shifts": int(counts[1] or 0),
            "closed_shifts": int(counts[2] or 0),
            "total_sales_base": total_sales,
            "cash_received_base": (positive_cash_sales or 0) + (cash_settlements or 0) + split_cash,
            "base_currency_code": base_currency_code,
            "variance_by_currency": [
                {"currency_code": row[0], "amount": row[1]}
                for row in variance_rows
            ],
        }

    async def base_currency_code(self, company_id):
        return (await self.db.execute(
            select(CompanyCurrency.code)
            .join(CompanySetting, CompanySetting.base_currency_id == CompanyCurrency.id)
            .where(CompanySetting.company_id == company_id, CompanyCurrency.company_id == company_id)
        )).scalar_one_or_none()

    async def has_open_device_shift(self, company_id, device_id):
        return (await self.db.execute(select(CashierShift.id).where(
            CashierShift.company_id == company_id,
            CashierShift.device_id == device_id,
            CashierShift.status == "open",
        ))).scalar_one_or_none() is not None
