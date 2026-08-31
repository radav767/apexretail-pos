import uuid
from fastapi import HTTPException

from app.models import Company, Shop, Branch, User, Employee, Device
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

        bundle = await self.repo.create_registration_bundle(
            company, shop, branch, user, employee, device
        )
        settings = get_settings()
        await SubscriptionService(
            self.repo.db,
            offline_grace_hours=settings.subscription_offline_grace_hours,
            provider_name=settings.subscription_provider_name,
        ).get_or_create_trial(company_id)

        token = create_access_token(str(user.id), user.email)

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
        }

    async def login(self, data):
        user = await self.repo.get_user_by_email(data.email.lower())

        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(401, "Invalid email or password")

        token = create_access_token(str(user.id), user.email)

        return {
            "ok": True,
            "token": token,
            "user": {"id": str(user.id), "email": user.email, "role": user.role},
            "company_id": str(user.company_id),
        }
