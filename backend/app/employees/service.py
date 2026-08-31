import hmac
import secrets
from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import HTTPException

from app.auth.security import (
    create_employee_access_token,
    hash_password,
    verify_password,
    create_session_token,
    hash_session_token,
)
from app.employees.repository import EmployeeRepository
from app.employees.schema import (
    EmployeeCreate,
    EmployeeUpdate,
    PinLoginRequest,
)
from app.models import Employee, Device, PosSession, AuditEvent, EmployeeShopAccess, Shop
from sqlalchemy import select


PERMISSION_KEYS = {
    "sales",
    "discounts",
    "refunds",
    "manage_inventory",
    "manage_products",
    "reports",
    "employees",
    "settings",
}


ROLE_PERMISSIONS = {
    "administrator": {
        "sales": True, "discounts": True, "refunds": True,
        "manage_inventory": True, "manage_products": True,
        "reports": True, "employees": True, "settings": True,
    },
    "cashier": {
        "sales": True,
        "discounts": False,
        "refunds": False,
        "manage_inventory": False,
        "manage_products": False,
        "reports": False,
        "employees": False,
        "settings": False,
    },
    "manager": {
        "sales": True,
        "discounts": True,
        "refunds": True,
        "manage_inventory": True,
        "manage_products": True,
        "reports": True,
        "employees": True,
        "settings": False,
    },
    "owner": {
        "sales": True,
        "discounts": True,
        "refunds": True,
        "manage_inventory": True,
        "manage_products": True,
        "reports": True,
        "employees": True,
        "settings": True,
    },
}


class EmployeeService:
    def __init__(
        self,
        repo: EmployeeRepository,
    ):
        self.repo = repo

    @staticmethod
    def clean_optional(
        value: str | None,
    ):
        if value is None:
            return None

        cleaned = value.strip()

        return cleaned or None

    @staticmethod
    def build_permissions(
        role: str,
        supplied: dict[str, bool] | None,
    ):
        permissions = dict(
            ROLE_PERMISSIONS.get(
                role,
                ROLE_PERMISSIONS["cashier"],
            )
        )

        if supplied:
            legacy_permissions = {
                "manage_inventory": supplied.get(
                    "manage_inventory",
                    supplied.get("inventory"),
                ),
                "manage_products": supplied.get(
                    "manage_products",
                    supplied.get("products"),
                ),
            }

            for key, value in legacy_permissions.items():
                if value is not None:
                    permissions[key] = bool(value)

            for key, value in supplied.items():
                if key in PERMISSION_KEYS:
                    permissions[key] = bool(value)

        return permissions

    def normalize_employee_view(
        self,
        row,
    ):
        if not row:
            return row

        return {
            **row,
            "permissions": self.build_permissions(
                row["role"],
                row["permissions"],
            ),
        }

    @staticmethod
    def verify_pin_value(
        entered_pin: str,
        stored_pin: str,
    ):
        if stored_pin.startswith("$2"):
            try:
                return verify_password(
                    entered_pin,
                    stored_pin,
                )
            except ValueError:
                return False

        return hmac.compare_digest(
            entered_pin,
            stored_pin,
        )

    async def ensure_unique_pin(
        self,
        company_id: UUID,
        pin: str,
        excluding_employee_id: UUID | None = None,
    ):
        employees = await self.repo.active_pin_candidates(
            company_id,
        )

        for employee in employees:
            if (
                excluding_employee_id is not None
                and employee.id == excluding_employee_id
            ):
                continue

            if self.verify_pin_value(
                pin,
                employee.pin,
            ):
                raise HTTPException(
                    409,
                    "This PIN is already used by another employee",
                )

    async def validate_location(
        self,
        company_id: UUID,
        shop_id: UUID,
        branch_id: UUID,
    ):
        location = await self.repo.get_location(
            company_id,
            shop_id,
            branch_id,
        )

        if not location:
            raise HTTPException(
                400,
                "The selected branch does not belong to the selected shop",
            )

    async def create(
        self,
        data: EmployeeCreate,
    ):
        await self.validate_location(
            data.company_id,
            data.shop_id,
            data.branch_id,
        )

        await self.ensure_unique_pin(
            data.company_id,
            data.pin,
        )

        employee = Employee(
            company_id=data.company_id,
            shop_id=data.shop_id,
            branch_id=data.branch_id,
            name=data.name.strip(),
            email=self.clean_optional(data.email),
            phone=self.clean_optional(data.phone),
            pin=hash_password(data.pin),
            role=data.role,
            permissions=self.build_permissions(
                data.role,
                data.permissions,
            ),
            active=True,
            deleted=False,
        )

        await self.repo.save(employee)

        return self.normalize_employee_view(
            await self.repo.get_view(
                data.company_id,
                employee.id,
            )
        )

    async def list_employees(
        self,
        company_id: UUID,
    ):
        rows = await self.repo.list_employees(
            company_id,
        )
        return [
            self.normalize_employee_view(row)
            for row in rows
        ]

    async def update(
        self,
        company_id: UUID,
        employee_id: UUID,
        data: EmployeeUpdate,
    ):
        employee = await self.repo.get_employee(
            company_id,
            employee_id,
        )

        if not employee:
            raise HTTPException(
                404,
                "Employee not found",
            )

        shop_id = data.shop_id or employee.shop_id
        branch_id = data.branch_id or employee.branch_id

        await self.validate_location(
            company_id,
            shop_id,
            branch_id,
        )

        if data.pin is not None:
            await self.ensure_unique_pin(
                company_id,
                data.pin,
                employee.id,
            )

            employee.pin = hash_password(
                data.pin,
            )

        if data.name is not None:
            employee.name = data.name.strip()

        if data.email is not None:
            employee.email = self.clean_optional(
                data.email,
            )

        if data.phone is not None:
            employee.phone = self.clean_optional(
                data.phone,
            )

        employee.shop_id = shop_id
        employee.branch_id = branch_id

        role_changed = (
            data.role is not None
            and data.role != employee.role
        )

        if data.role is not None:
            employee.role = data.role

        if (
            data.permissions is not None
            or role_changed
        ):
            employee.permissions = self.build_permissions(
                employee.role,
                data.permissions,
            )

        if data.active is not None:
            employee.active = data.active

        await self.repo.save(employee)

        return self.normalize_employee_view(
            await self.repo.get_view(
                company_id,
                employee.id,
            )
        )

    async def delete(
        self,
        company_id: UUID,
        employee_id: UUID,
    ):
        employee = await self.repo.get_employee(
            company_id,
            employee_id,
        )

        if not employee:
            raise HTTPException(
                404,
                "Employee not found",
            )

        if employee.role == "owner":
            raise HTTPException(
                400,
                "The owner employee cannot be deleted",
            )

        await self.repo.soft_delete(employee)

        return {
            "ok": True,
            "message": "Employee deleted",
        }

    async def pin_login(
        self,
        data: PinLoginRequest,
    ):
        employees = await self.repo.active_pin_candidates(data.company_id, data.branch_id)

        for employee in employees:
            if self.verify_pin_value(
                data.pin,
                employee.pin,
            ):
                permissions = self.build_permissions(
                    employee.role,
                    employee.permissions,
                )
                shop_id = data.shop_id or employee.shop_id
                if employee.role == "owner":
                    shops = (await self.repo.db.execute(select(Shop.id).where(Shop.company_id == data.company_id, Shop.active == True, Shop.deleted == False))).scalars().all()
                else:
                    shops = (await self.repo.db.execute(select(EmployeeShopAccess.shop_id).where(EmployeeShopAccess.employee_id == employee.id))).scalars().all() or [employee.shop_id]
                if shop_id not in shops:
                    raise HTTPException(403, "Employee is not authorised for this shop")
                shop_rows = (await self.repo.db.execute(select(Shop).where(Shop.id.in_(shops), Shop.company_id == data.company_id, Shop.active == True, Shop.deleted == False).order_by(Shop.name.asc()))).scalars().all()
                terminal_rows = (await self.repo.db.execute(select(Device).where(Device.company_id == data.company_id, Device.shop_id.in_(shops), Device.active == True, Device.deleted == False, Device.removed_at.is_(None), Device.deactivated_at.is_(None)).order_by(Device.shop_id, Device.pos_number.asc().nullslast()))).scalars().all()
                if data.shop_id is None and data.device_id is None:
                    return {"id": employee.id, "company_id": employee.company_id, "shop_id": None, "branch_id": None, "name": employee.name, "role": employee.role, "permissions": permissions, "access_token": "", "selection_required": True, "shops": [{"id": str(s.id), "name": s.name} for s in shop_rows], "terminals": [{"id": str(d.id), "shop_id": str(d.shop_id), "branch_id": str(d.branch_id), "name": d.friendly_name or d.name, "pos_number": d.pos_number} for d in terminal_rows]}
                q = select(Device).where(Device.company_id == data.company_id, Device.shop_id == shop_id, Device.active == True, Device.deleted == False, Device.removed_at.is_(None), Device.deactivated_at.is_(None))
                if data.device_id:
                    q = q.where(Device.id == data.device_id)
                device = (await self.repo.db.execute(q.order_by(Device.pos_number.asc().nullslast()))).scalars().first()
                if not device:
                    raise HTTPException(409, "No active POS terminal is available for this shop")
                now = datetime.now(timezone.utc)
                existing = (await self.repo.db.execute(select(PosSession).where(PosSession.employee_id == employee.id, PosSession.revoked_at.is_(None), PosSession.expires_at > now).with_for_update())).scalars().first()
                terminal_existing = (await self.repo.db.execute(select(PosSession).where(PosSession.device_id == device.id, PosSession.revoked_at.is_(None), PosSession.expires_at > now).with_for_update())).scalars().first()
                if existing and not data.takeover:
                    raise HTTPException(409, "You are already signed in on another device. Choose Cancel or Take over this session.")
                if terminal_existing and terminal_existing.id != (existing.id if existing else None) and not data.takeover:
                    raise HTTPException(409, "This POS terminal is already in use. Choose another terminal or take over the session.")
                if existing:
                    existing.revoked_at = now; existing.revoke_reason = "takeover"
                    self.repo.db.add(AuditEvent(company_id=data.company_id, actor_employee_id=employee.id, device_id=device.id, action="session_takeover", details={"old_device_id": str(existing.device_id), "new_device_id": str(device.id)}))
                if terminal_existing and terminal_existing.id != (existing.id if existing else None):
                    terminal_existing.revoked_at = now; terminal_existing.revoke_reason = "terminal_takeover"
                    self.repo.db.add(AuditEvent(company_id=data.company_id, actor_employee_id=employee.id, device_id=device.id, action="session_takeover", details={"old_device_id": str(device.id), "old_employee_id": str(terminal_existing.employee_id), "reason": "terminal_takeover"}))
                token = create_session_token()
                self.repo.db.add(PosSession(id=__import__('uuid').uuid4(), company_id=data.company_id, employee_id=employee.id, device_id=device.id, shop_id=device.shop_id, branch_id=device.branch_id, token_hash=hash_session_token(token), expires_at=now + timedelta(hours=12), last_authenticated_at=now))
                await self.repo.db.commit()
                return {
                    "id": employee.id,
                    "company_id": employee.company_id,
                    "shop_id": device.shop_id,
                    "branch_id": device.branch_id,
                    "name": employee.name,
                    "role": employee.role,
                    "permissions": permissions,
                    "access_token": token,
                    "device_id": device.id,
                }

        raise HTTPException(
            401,
            "Invalid employee PIN",
        )
