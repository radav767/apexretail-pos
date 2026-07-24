from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch
from app.models.device import Device
from app.models.shop import Shop


class DeviceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    def device_view_query(self):
        return (
            select(
                Device.id,
                Device.company_id,
                Device.shop_id,
                Device.branch_id,
                Shop.name.label("shop_name"),
                Branch.name.label("branch_name"),
                Device.name,
                Device.device_key,
                Device.platform,
                Device.app_version,
                Device.active,
            )
            .outerjoin(Shop, Shop.id == Device.shop_id)
            .outerjoin(Branch, Branch.id == Device.branch_id)
        )

    async def get_by_key(
        self,
        company_id: UUID,
        device_key: str,
    ):
        result = await self.db.execute(
            select(Device).where(
                Device.company_id == company_id,
                Device.device_key == device_key,
                Device.deleted == False,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        company_id: UUID,
        device_id: UUID,
    ):
        result = await self.db.execute(
            select(Device).where(
                Device.id == device_id,
                Device.company_id == company_id,
                Device.deleted == False,
            )
        )

        return result.scalar_one_or_none()

    async def get_view(
        self,
        company_id: UUID,
        device_id: UUID,
    ):
        result = await self.db.execute(
            self.device_view_query().where(
                Device.id == device_id,
                Device.company_id == company_id,
                Device.deleted == False,
            )
        )

        return result.mappings().first()

    async def list_devices(self, company_id: UUID):
        result = await self.db.execute(
            self.device_view_query()
            .where(
                Device.company_id == company_id,
                Device.deleted == False,
            )
            .order_by(Device.created_at.asc())
        )

        return result.mappings().all()

    async def get_shop(
        self,
        company_id: UUID,
        shop_id: UUID,
    ):
        result = await self.db.execute(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.company_id == company_id,
                Shop.active == True,
                Shop.deleted == False,
            )
        )

        return result.scalar_one_or_none()

    async def get_branch(
        self,
        company_id: UUID,
        branch_id: UUID,
    ):
        result = await self.db.execute(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.company_id == company_id,
                Branch.active == True,
                Branch.deleted == False,
            )
        )

        return result.scalar_one_or_none()

    async def create_device(
        self,
        *,
        company_id: UUID,
        shop_id: UUID,
        branch_id: UUID,
        device_key: str,
        name: str,
        platform: str,
        app_version: str,
    ):
        try:
            device = Device(
                company_id=company_id,
                shop_id=shop_id,
                branch_id=branch_id,
                device_key=device_key,
                name=name,
                platform=platform,
                app_version=app_version,
                active=True,
                deleted=False,
            )

            self.db.add(device)
            await self.db.commit()
            await self.db.refresh(device)

            return device
        except Exception:
            await self.db.rollback()
            raise

    async def update_registration(
        self,
        device: Device,
        *,
        name: str,
        platform: str,
        app_version: str,
    ):
        try:
            device.name = name
            device.platform = platform
            device.app_version = app_version
            device.active = True

            self.db.add(device)
            await self.db.commit()
            await self.db.refresh(device)

            return device
        except Exception:
            await self.db.rollback()
            raise

    async def update_assignment(
        self,
        device: Device,
        *,
        shop_id: UUID,
        branch_id: UUID,
    ):
        try:
            device.shop_id = shop_id
            device.branch_id = branch_id

            self.db.add(device)
            await self.db.commit()
            await self.db.refresh(device)

            return device
        except Exception:
            await self.db.rollback()
            raise
