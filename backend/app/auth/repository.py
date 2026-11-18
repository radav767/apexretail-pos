from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditEvent,
    Branch,
    Company,
    CompanyCurrency,
    CompanySetting,
    Device,
    DeviceTombstone,
    Employee,
    Shop,
    User,
)


class AuthRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str):
        result = await self.db.execute(
            select(User).where(User.email == email, User.active == True, User.deleted == False).with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_device_by_key(self, device_key: str):
        result = await self.db.execute(
            select(Device).where(Device.device_key == device_key)
        )
        return result.scalar_one_or_none()

    async def is_deleted_device_key(self, device_key_hash: str) -> bool:
        result = await self.db.execute(
            select(DeviceTombstone.id).where(DeviceTombstone.device_key_hash == device_key_hash)
        )
        return result.scalar_one_or_none() is not None

    async def create_registration_bundle(
        self,
        company: Company,
        shop: Shop,
        branch: Branch,
        user: User,
        employee: Employee,
        device: Device,
        base_currency: CompanyCurrency,
        company_settings: CompanySetting,
        audit_event: AuditEvent,
    ):
        self.db.add(company)
        await self.db.flush()

        self.db.add(shop)
        await self.db.flush()

        self.db.add(branch)
        await self.db.flush()

        self.db.add(user)
        await self.db.flush()

        self.db.add(base_currency)
        await self.db.flush()

        self.db.add(company_settings)
        self.db.add(employee)
        self.db.add(device)
        await self.db.flush()

        self.db.add(audit_event)
        await self.db.flush()

        return {
            "company": company,
            "shop": shop,
            "branch": branch,
            "user": user,
            "employee": employee,
            "device": device,
            "base_currency": base_currency,
            "company_settings": company_settings,
        }

    async def commit_registration(self):
        await self.db.commit()

    async def rollback_registration(self):
        await self.db.rollback()
