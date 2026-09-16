from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch
from app.models.device import Device
from app.models.device_tombstone import DeviceTombstone
from app.models.pos_session import PosSession
from app.models.sale import Sale
from app.models.device_activation_attempt import (
    DeviceActivationAttempt,
)
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
                Shop.address_line_1.label("shop_address_line_1"),
                Shop.address_line_2.label("shop_address_line_2"),
                Shop.city.label("shop_city"),
                Shop.state_province.label("shop_state_province"),
                Shop.country.label("shop_country"),
                Shop.phone.label("shop_phone"),
                Shop.tax_vat_number.label("shop_tax_vat_number"),
                Branch.name.label("branch_name"),
                Device.name,
                Device.friendly_name,
                Device.pos_number,
                Device.device_key,
                Device.platform,
                Device.app_version,
                Device.last_seen_at,
                Device.last_seen_platform,
                Device.last_seen_app_version,
                Device.status,
                Device.claimed_at,
                Device.deactivated_at,
                Device.deactivation_reason,
                Device.removed_at,
                Device.pending_shop_id,
                Device.pending_branch_id,
                Device.active,
                Device.assignment_revision,
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

    async def get_by_global_key(
        self,
        device_key: str,
        *,
        for_update: bool = False,
    ):
        statement = select(Device).where(
            Device.device_key == device_key,
            Device.deleted == False,
        )
        if for_update:
            statement = statement.with_for_update()

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def get_by_id(
        self,
        company_id: UUID,
        device_id: UUID,
        *,
        for_update: bool = False,
    ):
        statement = select(Device).where(
                Device.id == device_id,
                Device.company_id == company_id,
                Device.deleted == False,
            )
        if for_update:
            statement = statement.with_for_update()
        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def get_tombstone(self, company_id: UUID, device_id: UUID):
        result = await self.db.execute(
            select(DeviceTombstone).where(
                DeviceTombstone.id == device_id,
                DeviceTombstone.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def identity_is_tombstoned(
        self, device_key_hash: str, fingerprint_hash: str | None = None
    ) -> bool:
        predicates = [DeviceTombstone.device_key_hash == device_key_hash]
        if fingerprint_hash:
            predicates.append(DeviceTombstone.fingerprint_hash == fingerprint_hash)
        from sqlalchemy import or_
        result = await self.db.execute(select(DeviceTombstone.id).where(or_(*predicates)))
        return result.scalar_one_or_none() is not None

    async def deletion_dependencies(self, device_id: UUID):
        active_sessions = await self.db.scalar(
            select(func.count(PosSession.id)).where(
                PosSession.device_id == device_id,
                PosSession.revoked_at.is_(None),
                PosSession.expires_at > func.now(),
            )
        )
        historical_sales = await self.db.scalar(
            select(func.count(Sale.id)).where(Sale.device_id == device_id)
        )
        return int(active_sessions or 0), int(historical_sales or 0)

    async def revoke_sessions(self, device_id: UUID, now: datetime, reason: str):
        await self.db.execute(
            update(PosSession)
            .where(PosSession.device_id == device_id, PosSession.revoked_at.is_(None))
            .values(revoked_at=now, revoke_reason=reason)
        )

    async def delete_device_row(self, device_id: UUID):
        await self.db.execute(delete(Device).where(Device.id == device_id))

    async def get_by_fingerprint(
        self,
        company_id: UUID,
        device_fingerprint: str,
    ):
        result = await self.db.execute(
            select(Device).where(
                Device.company_id == company_id,
                Device.device_fingerprint == device_fingerprint,
                Device.deleted == False,
            )
        )

        return result.scalar_one_or_none()

    async def get_pending_activation(
        self,
        company_id: UUID,
        activation_code_hash: str,
        now: datetime,
        *,
        for_update: bool = False,
    ):
        statement = select(Device).where(
            Device.company_id == company_id,
            Device.activation_code_hash == activation_code_hash,
            Device.activation_code_expires_at.is_not(None),
            Device.activation_code_expires_at >= now,
            Device.deleted == False,
        )
        if for_update:
            statement = statement.with_for_update()

        result = await self.db.execute(statement)

        return result.scalar_one_or_none()

    async def get_activation_attempt(
        self,
        company_id: UUID,
        device_fingerprint: str,
        *,
        for_update: bool = False,
    ):
        statement = select(DeviceActivationAttempt).where(
            DeviceActivationAttempt.company_id == company_id,
            DeviceActivationAttempt.device_fingerprint
            == device_fingerprint,
            DeviceActivationAttempt.deleted == False,
        )
        if for_update:
            statement = statement.with_for_update()

        result = await self.db.execute(statement)
        return result.scalar_one_or_none()

    async def ensure_activation_attempt(
        self,
        company_id: UUID,
        device_fingerprint: str,
    ):
        await self.db.execute(
            insert(DeviceActivationAttempt)
            .values(
                company_id=company_id,
                device_fingerprint=device_fingerprint,
                failed_attempts=0,
                active=True,
                deleted=False,
            )
            .on_conflict_do_nothing(
                constraint=(
                    "uq_device_activation_attempts_company_fingerprint"
                )
            )
        )

    async def delete_activation_attempt(
        self,
        company_id: UUID,
        device_fingerprint: str,
    ):
        await self.db.execute(
            delete(DeviceActivationAttempt).where(
                DeviceActivationAttempt.company_id == company_id,
                DeviceActivationAttempt.device_fingerprint
                == device_fingerprint,
            )
        )

    async def find_branch_pos_number_device(
        self,
        company_id: UUID,
        branch_id: UUID,
        pos_number: int,
        *,
        exclude_device_id: UUID | None = None,
    ):
        statement = select(Device).where(
            Device.company_id == company_id,
            Device.branch_id == branch_id,
            Device.pos_number == pos_number,
            Device.removed_at.is_(None),
            Device.deleted == False,
        )
        if exclude_device_id is not None:
            statement = statement.where(
                Device.id != exclude_device_id
            )

        result = await self.db.execute(statement)
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
        friendly_name: str | None,
        pos_number: int | None,
        platform: str,
        app_version: str,
        status: str = "active",
        active: bool = True,
        claimed_at: datetime | None = None,
        activation_code_hash: str | None = None,
        activation_code_expires_at: datetime | None = None,
        device_fingerprint: str | None = None,
        pending_shop_id: UUID | None = None,
        pending_branch_id: UUID | None = None,
        last_seen_at: datetime | None = None,
    ):
        try:
            device = Device(
                company_id=company_id,
                shop_id=shop_id,
                branch_id=branch_id,
                device_key=device_key,
                name=name,
                friendly_name=friendly_name,
                pos_number=pos_number,
                platform=platform,
                app_version=app_version,
                last_seen_at=last_seen_at,
                last_seen_platform=platform if last_seen_at else None,
                last_seen_app_version=app_version if last_seen_at else None,
                status=status,
                claimed_at=claimed_at,
                activation_code_hash=activation_code_hash,
                activation_code_expires_at=activation_code_expires_at,
                device_fingerprint=device_fingerprint,
                pending_shop_id=pending_shop_id,
                pending_branch_id=pending_branch_id,
                active=active,
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
        device_fingerprint: str | None,
        platform: str,
        app_version: str,
        last_seen_at: datetime,
    ):
        try:
            device.name = name
            device.friendly_name = device.friendly_name or name
            device.platform = platform
            device.app_version = app_version
            device.device_fingerprint = (
                device_fingerprint or device.device_fingerprint
            )
            device.last_seen_at = last_seen_at
            device.last_seen_platform = platform
            device.last_seen_app_version = app_version

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
        friendly_name: str | None,
        pos_number: int | None,
        shop_id: UUID,
        branch_id: UUID,
    ):
        try:
            device.friendly_name = friendly_name
            device.pos_number = pos_number
            device.shop_id = shop_id
            device.branch_id = branch_id

            self.db.add(device)
            await self.db.commit()
            await self.db.refresh(device)

            return device
        except Exception:
            await self.db.rollback()
            raise

    async def save(self, device: Device):
        try:
            self.db.add(device)
            await self.db.commit()
            await self.db.refresh(device)
            return device
        except Exception:
            await self.db.rollback()
            raise

    async def flush(self, device: Device | None = None):
        if device is not None:
            self.db.add(device)
        await self.db.flush()
