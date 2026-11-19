from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Branch, Device, DeviceTombstone, Employee, EmployeeDeviceAccess,
    EmployeeRole, Shop,
)


class EmployeeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def authorize_actor(self, company_id, actor):
        from app.sales.commands import actor_identity
        from app.printing.service import permit
        actor_identity(actor, company_id)
        permit(actor, 'employees_manage')

    async def revoke_sessions(self, employee, reason):
        from .revocation import revoke
        employee.session_version = await revoke(self.db, employee.company_id, employee.id, reason)
        return employee.session_version

    def view_query(self):
        return (
            select(
                Employee.id,
                Employee.company_id,
                Employee.shop_id,
                Employee.branch_id,
                Shop.name.label("shop_name"),
                Branch.name.label("branch_name"),
                Employee.name,
                Employee.email,
                Employee.phone,
                Employee.role,
                Employee.role_id,
                EmployeeRole.name.label("role_name"),
                Employee.permissions,
                Employee.device_restricted,
                Employee.active,
            )
            .join(
                Shop,
                Shop.id == Employee.shop_id,
            )
            .join(
                Branch,
                Branch.id == Employee.branch_id,
            )
            .outerjoin(EmployeeRole, EmployeeRole.id == Employee.role_id)
        )

    async def is_deleted_device_identity(
        self,
        company_id: UUID,
        *,
        device_id: UUID | None,
        device_key_hash: str | None,
    ) -> bool:
        predicates = []
        if device_id is not None:
            predicates.append(DeviceTombstone.id == device_id)
        if device_key_hash is not None:
            predicates.append(DeviceTombstone.device_key_hash == device_key_hash)
        if not predicates:
            return False
        result = await self.db.execute(
            select(DeviceTombstone.id).where(
                DeviceTombstone.company_id == company_id,
                or_(*predicates),
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_employees(
        self,
        company_id: UUID,
    ):
        result = await self.db.execute(
            self.view_query()
            .where(
                Employee.company_id == company_id,
                Employee.deleted == False,
            )
            .order_by(Employee.name.asc())
        )

        return result.mappings().all()

    async def get_view(
        self,
        company_id: UUID,
        employee_id: UUID,
    ):
        result = await self.db.execute(
            self.view_query().where(
                Employee.id == employee_id,
                Employee.company_id == company_id,
                Employee.deleted == False,
            )
        )

        return result.mappings().first()

    async def get_employee(
        self,
        company_id: UUID,
        employee_id: UUID,
    ):
        result = await self.db.execute(
            select(Employee).where(
                Employee.id == employee_id,
                Employee.company_id == company_id,
                Employee.deleted == False,
            )
        )

        return result.scalar_one_or_none()

    async def get_location(
        self,
        company_id: UUID,
        shop_id: UUID,
        branch_id: UUID,
    ):
        result = await self.db.execute(
            select(Shop, Branch)
            .join(
                Branch,
                Branch.shop_id == Shop.id,
            )
            .where(
                Shop.id == shop_id,
                Shop.company_id == company_id,
                Shop.active == True,
                Shop.deleted == False,
                Branch.id == branch_id,
                Branch.company_id == company_id,
                Branch.active == True,
                Branch.deleted == False,
            )
        )

        return result.first()

    async def get_role(self, company_id: UUID, role_id: UUID):
        result = await self.db.execute(select(EmployeeRole).where(
            EmployeeRole.id == role_id,
            EmployeeRole.company_id == company_id,
            EmployeeRole.active == True,
            EmployeeRole.deleted == False,
        ))
        return result.scalar_one_or_none()

    async def validate_devices(self, company_id: UUID, device_ids: list[UUID]):
        if not device_ids:
            return []
        result = await self.db.execute(select(Device.id).where(
            Device.company_id == company_id,
            Device.id.in_(set(device_ids)),
            Device.active == True,
            Device.deleted == False,
            Device.removed_at.is_(None),
        ))
        found = list(result.scalars().all())
        if len(set(found)) != len(set(device_ids)):
            return None
        return found

    async def device_ids(self, employee_id: UUID):
        result = await self.db.execute(select(EmployeeDeviceAccess.device_id).where(
            EmployeeDeviceAccess.employee_id == employee_id,
        ))
        return list(result.scalars().all())

    async def set_devices(self, employee: Employee, device_ids: list[UUID]):
        await self.db.execute(
            __import__("sqlalchemy").delete(EmployeeDeviceAccess).where(
                EmployeeDeviceAccess.employee_id == employee.id
            )
        )
        for device_id in set(device_ids):
            self.db.add(EmployeeDeviceAccess(
                company_id=employee.company_id,
                employee_id=employee.id,
                device_id=device_id,
            ))

    async def device_allowed(self, employee_id: UUID, device_id: UUID):
        result = await self.db.execute(select(EmployeeDeviceAccess.id).where(
            EmployeeDeviceAccess.employee_id == employee_id,
            EmployeeDeviceAccess.device_id == device_id,
        ))
        return result.scalar_one_or_none() is not None

    async def active_pin_candidates(
        self,
        company_id: UUID,
        branch_id: UUID | None = None,
    ):
        query = select(Employee).where(
            Employee.company_id == company_id,
            Employee.active == True,
            Employee.deleted == False,
        )

        if branch_id is not None:
            query = query.where(
                or_(
                    Employee.branch_id == branch_id,
                    Employee.role.in_(
                        ["owner", "manager"],
                    ),
                )
            )

        result = await self.db.execute(query)

        return result.scalars().all()

    async def save(self, employee: Employee):
        try:
            self.db.add(employee)
            await self.db.commit()
            await self.db.refresh(employee)

            return employee
        except Exception:
            await self.db.rollback()
            raise

    async def soft_delete(
        self,
        employee: Employee,
    ):
        try:
            employee.deleted = True
            employee.active = False

            self.db.add(employee)
            await self.db.commit()

            return employee
        except Exception:
            await self.db.rollback()
            raise
