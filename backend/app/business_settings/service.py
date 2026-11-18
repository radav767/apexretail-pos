from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_settings.schema import CompanySettingsUpdate
from app.subscriptions.write_policy import require_new_write
from app.models.company import Company
from app.models.company_settings import CompanySetting
from app.models.shop import Shop


ALLOWED_PAYMENT_METHODS = {
    "cash",
    "card",
    "mobile",
    "credit",
    "cheque",
    "split",
}


class BusinessSettingsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_company(self, company_id: UUID) -> Company:
        result = await self.db.execute(
            select(Company).where(
                Company.id == company_id,
                Company.active.is_(True),
                Company.deleted.is_(False),
            )
        )
        company = result.scalar_one_or_none()

        if company is None:
            raise HTTPException(404, "Company not found")

        return company

    async def get_or_create_setting(
        self,
        company_id: UUID,
        *, commit: bool = True,
    ) -> CompanySetting:
        result = await self.db.execute(
            select(CompanySetting).where(
                CompanySetting.company_id == company_id,
                CompanySetting.deleted.is_(False),
            )
        )
        setting = result.scalar_one_or_none()

        if setting is None:
            setting = CompanySetting(company_id=company_id)
            self.db.add(setting)
            if commit: await self.db.commit()
            else: await self.db.flush()
            await self.db.refresh(setting)

        return setting

    @staticmethod
    def clean_optional(value):
        if value is None:
            return None

        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None

        return value

    @staticmethod
    def serialize(
        company: Company,
        setting: CompanySetting,
    ) -> dict:
        return {
            "company_id": company.id,
            "name": company.name,
            "owner_name": company.owner_name,
            "owner_email": company.owner_email,
            "business_type": company.business_type,
            "country": company.country,
            "phone": company.phone,
            "address": setting.address,
            "contact_email": setting.contact_email or company.owner_email,
            "currency_code": setting.currency_code,
            "currency_symbol": setting.currency_symbol,
            "decimal_places": setting.decimal_places,
            "tax_name": setting.tax_name,
            "tax_rate": setting.tax_rate,
            "tax_inclusive": setting.tax_inclusive,
            "receipt_header": setting.receipt_header,
            "receipt_footer": setting.receipt_footer,
            "paper_size": setting.paper_size,
            "auto_print": setting.auto_print,
            "payment_methods": setting.payment_methods,
            "base_currency_id": setting.base_currency_id,
            "currency_config_version": setting.currency_config_version,
            "multi_currency_enabled": setting.multi_currency_enabled,
            "shift_enforcement_enabled": setting.shift_enforcement_enabled,
            "shift_required_from": setting.shift_required_from,
            "reporting_timezone": setting.reporting_timezone,
        }

    @staticmethod
    def serialize_company_profile(
        company: Company,
        setting: CompanySetting,
    ) -> dict:
        return {
            "company_id": company.id,
            "name": company.name,
            "owner_name": company.owner_name,
            "owner_email": company.owner_email,
            "business_type": company.business_type,
            "country": company.country,
            "phone": company.phone,
            "contact_email": setting.contact_email or company.owner_email,
        }

    @staticmethod
    def serialize_receipt_settings(
        company_id: UUID,
        setting: CompanySetting,
    ) -> dict:
        return {
            "company_id": company_id,
            "receipt_header": setting.receipt_header,
            "receipt_footer": setting.receipt_footer,
            "paper_size": setting.paper_size,
            "auto_print": setting.auto_print,
            "tax_name": setting.tax_name,
            "tax_rate": setting.tax_rate,
            "tax_inclusive": setting.tax_inclusive,
            "payment_methods": setting.payment_methods,
        }

    @staticmethod
    def serialize_shop(shop: Shop) -> dict:
        return {
            "id": shop.id,
            "company_id": shop.company_id,
            "name": shop.name,
            "address_line_1": shop.address_line_1,
            "address_line_2": shop.address_line_2,
            "city": shop.city,
            "state_province": shop.state_province,
            "country": shop.country,
            "phone": shop.phone,
            "tax_vat_number": shop.tax_vat_number,
            "active": shop.active,
        }

    async def get(self, company_id: UUID, *, commit: bool = True) -> dict:
        company = await self.get_company(company_id)
        setting = await self.get_or_create_setting(company_id, commit=commit)
        return self.serialize(company, setting)

    async def get_company_profile(self, company_id: UUID) -> dict:
        company = await self.get_company(company_id)
        setting = await self.get_or_create_setting(company_id)
        return self.serialize_company_profile(company, setting)

    async def get_receipt_settings(self, company_id: UUID) -> dict:
        await self.get_company(company_id)
        setting = await self.get_or_create_setting(company_id)
        return self.serialize_receipt_settings(company_id, setting)

    async def list_shops(self, company_id: UUID) -> list[dict]:
        await self.get_company(company_id)
        result = await self.db.execute(
            select(Shop).where(
                Shop.company_id == company_id,
                Shop.deleted.is_(False),
            ).order_by(Shop.created_at.asc())
        )
        return [
            self.serialize_shop(shop)
            for shop in result.scalars().all()
        ]

    async def update(
        self,
        company_id: UUID,
        data: CompanySettingsUpdate,
    ) -> dict:
        await require_new_write(self.db, company_id)
        company = await self.get_company(company_id)
        setting = await self.get_or_create_setting(company_id, commit=False)
        values = data.model_dump(exclude_unset=True)

        if setting.base_currency_id is not None and any(
            field in values for field in ("currency_code", "currency_symbol", "decimal_places")
        ):
            raise HTTPException(
                409,
                "Manage base currency, symbol, and decimal precision through Currency Settings",
            )

        company_fields = {
            "name",
            "owner_name",
            "business_type",
            "country",
            "phone",
        }

        setting_fields = {
            "address",
            "contact_email",
            "currency_code",
            "currency_symbol",
            "decimal_places",
            "tax_name",
            "tax_rate",
            "tax_inclusive",
            "receipt_header",
            "receipt_footer",
            "paper_size",
            "auto_print",
            "payment_methods",
            "multi_currency_enabled",
            "shift_enforcement_enabled",
            "shift_required_from",
            "reporting_timezone",
        }

        for field in company_fields:
            if field not in values:
                continue

            value = self.clean_optional(values[field])

            if field in {"name", "business_type"} and value is None:
                raise HTTPException(
                    400,
                    f"{field.replace('_', ' ').title()} cannot be empty",
                )

            setattr(company, field, value)

        for field in setting_fields:
            if field not in values:
                continue

            value = values[field]

            if field == "payment_methods":
                normalized = []
                for method in value or []:
                    method_name = str(method).strip().lower()

                    if method_name not in ALLOWED_PAYMENT_METHODS:
                        raise HTTPException(
                            400,
                            f"Unsupported payment method: {method_name}",
                        )

                    if method_name not in normalized:
                        normalized.append(method_name)

                if not normalized:
                    raise HTTPException(
                        400,
                        "At least one payment method is required",
                    )

                value = normalized

            elif field == "currency_code" and value is not None:
                value = value.strip().upper()

            elif isinstance(value, str):
                value = self.clean_optional(value)

            setattr(setting, field, value)

        try:
            self.db.add(company)
            self.db.add(setting)
            await self.db.commit()
            await self.db.refresh(company)
            await self.db.refresh(setting)
        except Exception:
            await self.db.rollback()
            raise

        return self.serialize(company, setting)

    async def update_company_profile(
        self,
        company_id: UUID,
        data,
    ) -> dict:
        await require_new_write(self.db, company_id)
        company = await self.get_company(company_id)
        setting = await self.get_or_create_setting(company_id, commit=False)
        values = data.model_dump(exclude_unset=True)

        for field in {
            "name",
            "owner_name",
            "business_type",
            "country",
            "phone",
        }:
            if field not in values:
                continue

            value = self.clean_optional(values[field])

            if field in {"name", "business_type"} and value is None:
                raise HTTPException(
                    400,
                    f"{field.replace('_', ' ').title()} cannot be empty",
                )

            setattr(company, field, value)

        if "contact_email" in values:
            setting.contact_email = self.clean_optional(
                values["contact_email"]
            )

        try:
            self.db.add(company)
            self.db.add(setting)
            await self.db.commit()
            await self.db.refresh(company)
            await self.db.refresh(setting)
        except Exception:
            await self.db.rollback()
            raise

        return self.serialize_company_profile(company, setting)

    async def update_receipt_settings(
        self,
        company_id: UUID,
        data,
    ) -> dict:
        await require_new_write(self.db, company_id)
        await self.get_company(company_id)
        setting = await self.get_or_create_setting(company_id, commit=False)
        values = data.model_dump(exclude_unset=True)

        for field in values:
            value = values[field]

            if field == "payment_methods":
                normalized = []
                for method in value or []:
                    method_name = str(method).strip().lower()

                    if method_name not in ALLOWED_PAYMENT_METHODS:
                        raise HTTPException(
                            400,
                            f"Unsupported payment method: {method_name}",
                        )

                    if method_name not in normalized:
                        normalized.append(method_name)

                if not normalized:
                    raise HTTPException(
                        400,
                        "At least one payment method is required",
                    )

                value = normalized
            elif isinstance(value, str):
                value = self.clean_optional(value)

            setattr(setting, field, value)

        try:
            self.db.add(setting)
            await self.db.commit()
            await self.db.refresh(setting)
        except Exception:
            await self.db.rollback()
            raise

        return self.serialize_receipt_settings(company_id, setting)

    async def update_shop(
        self,
        company_id: UUID,
        shop_id: UUID,
        data,
    ) -> dict:
        await require_new_write(self.db, company_id)
        await self.get_company(company_id)
        result = await self.db.execute(
            select(Shop).where(
                Shop.id == shop_id,
                Shop.company_id == company_id,
                Shop.deleted.is_(False),
            )
        )
        shop = result.scalar_one_or_none()

        if shop is None:
            raise HTTPException(404, "Shop not found")

        values = data.model_dump(exclude_unset=True)
        for field, value in values.items():
            cleaned = self.clean_optional(value)
            if field == "name" and cleaned is None:
                raise HTTPException(
                    400,
                    "Shop name cannot be empty",
                )
            setattr(shop, field, cleaned)

        try:
            self.db.add(shop)
            await self.db.commit()
            await self.db.refresh(shop)
        except Exception:
            await self.db.rollback()
            raise

        return self.serialize_shop(shop)
