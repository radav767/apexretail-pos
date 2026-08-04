import uuid
from fastapi import HTTPException

from app.models import Company, Shop, Branch, User, Employee, Device
from app.auth.repository import AuthRepository
from app.auth.security import hash_password, verify_password, create_access_token


class AuthService:
    def __init__(self, repo: AuthRepository):
        self.repo = repo

    async def register(self, data):
        if data.password != data.confirm_password:
            raise HTTPException(400, "Passwords do not match")

        owner_name = data.owner_name.strip()
        owner_pin = data.owner_pin.strip()

        if len(owner_name) < 2:
            raise HTTPException(400, "Owner name is required")

        if len(owner_pin) != 4 or not owner_pin.isdigit():
            raise HTTPException(400, "Owner PIN must contain exactly 4 digits")

        existing = await self.repo.get_user_by_email(data.email.lower())
        if existing:
            raise HTTPException(409, "Email already registered")

        owner_name = (
            data.owner_name.strip()
            if data.owner_name and data.owner_name.strip()
            else data.email.split("@")[0]
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
            name=data.business_name,
            owner_name=data.owner_name.strip(),
            owner_email=data.email.lower(),
            business_type=data.business_type,
            country=data.country,
            phone=data.phone,
        )

        shop = Shop(id=shop_id, company_id=company_id, name="Main Shop")
        branch = Branch(id=branch_id, company_id=company_id, shop_id=shop_id, name="Main Branch")

        user = User(
            id=user_id,
            company_id=company_id,
            email=data.email.lower(),
            password_hash=hash_password(data.password),
            role="owner",
        )

        employee = Employee(
            id=employee_id,
            company_id=company_id,
            shop_id=shop_id,
            branch_id=branch_id,
            name=data.owner_name.strip(),
            email=data.email.lower(),
            pin=hash_password(data.owner_pin),
            role="owner",
        )

        device = Device(
            id=device_id,
            company_id=company_id,
            shop_id=shop_id,
            branch_id=branch_id,
            name="Main Device",
            device_key=data.device_key or str(uuid.uuid4()),
            platform="Web",
            app_version="1.0.0",
        )

        bundle = await self.repo.create_registration_bundle(
            company, shop, branch, user, employee, device
        )

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
