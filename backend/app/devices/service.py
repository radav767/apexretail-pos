from uuid import UUID

from fastapi import HTTPException

from app.devices.repository import DeviceRepository
from app.devices.schema import (
    DeviceAssignmentUpdate,
    DeviceRegister,
)
from app.inventory.stock_repository import BranchStockRepository


class DeviceService:
    def __init__(self, repo: DeviceRepository):
        self.repo = repo
        self.stock = BranchStockRepository(repo.db)

    async def register(self, data: DeviceRegister):
        device_key = data.device_key.strip()
        name = data.name.strip()
        platform = data.platform.strip() or "web"
        app_version = data.app_version.strip() or "1.0.0"

        existing = await self.repo.get_by_key(
            data.company_id,
            device_key,
        )

        if existing:
            await self.repo.update_registration(
                existing,
                name=name,
                platform=platform,
                app_version=app_version,
            )

            return await self.repo.get_view(
                data.company_id,
                existing.id,
            )

        default_branch = await self.stock.resolve_branch(
            data.company_id,
            None,
        )

        device = await self.repo.create_device(
            company_id=data.company_id,
            shop_id=default_branch.shop_id,
            branch_id=default_branch.id,
            device_key=device_key,
            name=name,
            platform=platform,
            app_version=app_version,
        )

        return await self.repo.get_view(
            data.company_id,
            device.id,
        )

    async def list_devices(self, company_id: UUID):
        return await self.repo.list_devices(company_id)

    async def assign(
        self,
        company_id: UUID,
        device_id: UUID,
        data: DeviceAssignmentUpdate,
    ):
        device = await self.repo.get_by_id(
            company_id,
            device_id,
        )

        if not device:
            raise HTTPException(404, "Device not found")

        shop = await self.repo.get_shop(
            company_id,
            data.shop_id,
        )

        if not shop:
            raise HTTPException(
                404,
                "Shop not found or inactive",
            )

        branch = await self.repo.get_branch(
            company_id,
            data.branch_id,
        )

        if not branch:
            raise HTTPException(
                404,
                "Branch not found or inactive",
            )

        if branch.shop_id != shop.id:
            raise HTTPException(
                400,
                "The selected branch does not belong to the selected shop",
            )

        await self.repo.update_assignment(
            device,
            shop_id=shop.id,
            branch_id=branch.id,
        )

        return await self.repo.get_view(
            company_id,
            device.id,
        )
