import uuid
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.auth.registration_currencies import REGISTRATION_CURRENCY_BY_CODE
from app.models import (
    AuditEvent,
    Branch,
    Company,
    CompanyCurrency,
    CompanySetting,
    Device,
    Employee,
    Shop,
    User,
)
from app.auth.repository import AuthRepository
from app.auth.security import (
    create_access_token,
    create_employee_access_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings
from app.employees.service import EmployeeService
from app.subscriptions.service import SubscriptionService
from app.devices.authority import (
    TERMINAL_IDENTITY_REVOKED,
    hash_device_identity,
    terminal_authority_error,
)


class AuthService:
    def __init__(self, repo: AuthRepository):
        self.repo = repo

    async def register(self, data):
        if data.password != data.confirm_password:
            raise HTTPException(400, "Passwords do not match")

        owner_name = data.owner_name
        owner_pin = data.owner_pin.strip()
        business_name = data.business_name
        business_type = data.business_type
        country = data.country
        phone = data.phone
        email = str(data.email)

        if len(owner_name) < 2:
            raise HTTPException(400, "Owner name is required")

        if len(owner_pin) != 4 or not owner_pin.isdigit():
            raise HTTPException(400, "Owner PIN must contain exactly 4 digits")

        existing = await self.repo.get_user_by_email(email)
        if existing:
            raise HTTPException(409, "Email already registered")

        owner_name = (
            owner_name
            if owner_name
            else email.split("@")[0]
        )
        owner_pin = data.owner_pin or "1234"

        company_id = uuid.uuid4()
        shop_id = uuid.uuid4()
        branch_id = uuid.uuid4()
        user_id = uuid.uuid4()
        employee_id = uuid.uuid4()
        device_id = uuid.uuid4()
        base_currency_id = uuid.uuid4()

        company = Company(
            id=company_id,
            name=business_name,
            owner_name=owner_name,
            owner_email=email,
            business_type=business_type,
            country=country,
            phone=phone,
        )

        shop = Shop(id=shop_id, company_id=company_id, name="Main Shop")
        branch = Branch(id=branch_id, company_id=company_id, shop_id=shop_id, name="Main Branch")

        user = User(
            id=user_id,
            company_id=company_id,
            email=email,
            password_hash=hash_password(data.password),
            role="owner",
        )

        currency_definition = REGISTRATION_CURRENCY_BY_CODE[
            data.base_currency_code
        ]
        base_currency = CompanyCurrency(
            id=base_currency_id,
            company_id=company_id,
            code=currency_definition.code,
            display_name=currency_definition.display_name,
            symbol=currency_definition.symbol,
            decimal_places=currency_definition.decimal_places,
            active=True,
            is_base=True,
            cash_accepted=True,
            card_accepted=True,
            mobile_accepted=True,
            display_order=0,
            created_by_user_id=user_id,
        )
        company_settings = CompanySetting(
            company_id=company_id,
            base_currency_id=base_currency_id,
            currency_code=currency_definition.code,
            currency_symbol=currency_definition.symbol,
            decimal_places=currency_definition.decimal_places,
            currency_config_version=1,
            multi_currency_enabled=False,
            shift_enforcement_enabled=False,
            contact_email=email,
        )

        employee = Employee(
            id=employee_id,
            company_id=company_id,
            shop_id=shop_id,
            branch_id=branch_id,
            name=owner_name,
            email=email,
            pin=hash_password(data.owner_pin),
            role="owner",
        )

        requested_device_key = data.device_key or ""

        registration_device_key = requested_device_key or str(uuid.uuid4())

        if requested_device_key:
            if await self.repo.is_deleted_device_key(hash_device_identity(requested_device_key)):
                raise terminal_authority_error(
                    403,
                    TERMINAL_IDENTITY_REVOKED,
                    "This terminal identity was permanently deleted",
                )
            existing_device = await self.repo.get_device_by_key(
                requested_device_key
            )

            # A device key is globally unique. A new business registration
            # must never try to reuse a key already owned by another record.
            if existing_device:
                registration_device_key = str(uuid.uuid4())

        device = Device(
            id=device_id,
            company_id=company_id,
            shop_id=shop_id,
            branch_id=branch_id,
            name="Main Device",
            device_key=registration_device_key,
            platform="Web",
            app_version="1.0.0",
        )

        audit_event = AuditEvent(
            company_id=company_id,
            actor_user_id=user_id,
            actor_employee_id=employee_id,
            device_id=device_id,
            action="company_registered",
            details={
                "base_currency": currency_definition.code,
                "decimal_places": currency_definition.decimal_places,
            },
        )

        try:
            await self.repo.create_registration_bundle(
                company,
                shop,
                branch,
                user,
                employee,
                device,
                base_currency,
                company_settings,
                audit_event,
            )
            settings = get_settings()
            await SubscriptionService(
                self.repo.db,
                offline_grace_hours=settings.subscription_offline_grace_hours,
                provider_name=settings.subscription_provider_name,
            ).get_or_create_trial(company_id, commit=False)
            await self.repo.commit_registration()
        except IntegrityError as exc:
            await self.repo.rollback_registration()
            raise HTTPException(
                409,
                "Registration conflicts with an existing account or terminal",
            ) from exc
        except Exception:
            await self.repo.rollback_registration()
            raise

        token = create_access_token(str(user.id), user.email, session_version=user.session_version)

        return {
            "ok": True,
            "token": token,
            "company": {"id": str(company.id), "name": company.name},
            "shop": {"id": str(shop.id), "name": shop.name},
            "branch": {"id": str(branch.id), "name": branch.name},
            "user": {"id": str(user.id), "email": user.email, "role": user.role},
            "employee": {
                "id": str(employee.id),
                "name": employee.name,
                "role": employee.role,
                "permissions": EmployeeService.build_permissions(
                    employee.role,
                    employee.permissions,
                ),
                "access_token": create_employee_access_token(
                    employee_id=str(employee.id),
                    company_id=str(employee.company_id),
                    role=employee.role,
                ),
            },
            "device": {"id": str(device.id), "name": device.name, "device_key": device.device_key},
            "base_currency": {
                "code": base_currency.code,
                "symbol": base_currency.symbol,
                "decimal_places": base_currency.decimal_places,
            },
        }

    async def login(self, data):
        user = await self.repo.get_user_by_email(data.email.lower())

        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(401, "Invalid email or password")

        token = create_access_token(str(user.id), user.email, session_version=user.session_version)

        return {
            "ok": True,
            "token": token,
            "user": {"id": str(user.id), "email": user.email, "role": user.role},
            "company_id": str(user.company_id),
        }
