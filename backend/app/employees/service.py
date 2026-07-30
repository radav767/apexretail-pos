import hmac
from uuid import UUID

from fastapi import HTTPException

from app.auth.security import (
    hash_password,
    verify_password,
)
from app.employees.repository import EmployeeRepository
from app.employees.schema import (
    EmployeeCreate,
    EmployeeUpdate,
    PinLoginRequest,
)
from app.models import Employee


PERMISSION_KEYS = {
    "sales",
    "discounts",
    "refunds",
    "inventory",
    "products",
    "reports",
    "employees",
    "settings",
}


ROLE_PERMISSIONS = {
    "cashier": {
        "sales": True,
        "discounts": False,
        "refunds": False,
        "inventory": False,
        "products": False,
        "reports": False,
        "employees": False,
        "settings": False,
    },
    "manager": {
        "sales": True,
        "discounts": True,
        "refunds": True,
        "inventory": True,
        "products": True,
        "reports": True,
        "employees": True,
        "settings": False,
    },
    "owner": {
        "sales": True,
        "discounts": True,
        "refunds": True,
        "inventory": True,
        "products": True,
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
            for key, value in supplied.items():
                if key in PERMISSION_KEYS:
                    permissions[key] = bool(value)

        return permissions

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

        return await self.repo.get_view(
            data.company_id,
            employee.id,
        )

    async def list_employees(
        self,
        company_id: UUID,
    ):
        return await self.repo.list_employees(
            company_id,
        )

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

        return await self.repo.get_view(
            company_id,
            employee.id,
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
        employees = await self.repo.active_pin_candidates(
            data.company_id,
            data.branch_id,
        )

        for employee in employees:
            if self.verify_pin_value(
                data.pin,
                employee.pin,
            ):
                return {
                    "id": employee.id,
                    "company_id": employee.company_id,
                    "shop_id": employee.shop_id,
                    "branch_id": employee.branch_id,
                    "name": employee.name,
                    "role": employee.role,
                    "permissions": employee.permissions
                    or self.build_permissions(
                        employee.role,
                        None,
                    ),
                }

        raise HTTPException(
            401,
            "Invalid employee PIN",
        )
