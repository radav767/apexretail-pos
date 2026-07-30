from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Branch, Employee, Shop


class EmployeeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

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
                Employee.permissions,
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
        )

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
