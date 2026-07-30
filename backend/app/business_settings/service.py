from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business_settings.schema import CompanySettingsUpdate
from app.models.company import Company
from app.models.company_settings import CompanySetting


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
            await self.db.commit()
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
        }

    async def get(self, company_id: UUID) -> dict:
        company = await self.get_company(company_id)
        setting = await self.get_or_create_setting(company_id)
        return self.serialize(company, setting)

    async def update(
        self,
        company_id: UUID,
        data: CompanySettingsUpdate,
    ) -> dict:
        company = await self.get_company(company_id)
        setting = await self.get_or_create_setting(company_id)
        values = data.model_dump(exclude_unset=True)

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
