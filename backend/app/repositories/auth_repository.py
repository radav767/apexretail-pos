from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, Shop, Branch, User, Employee, Device


class AuthRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str):
        result = await self.db.execute(
            select(User).where(User.email == email, User.active == True, User.deleted == False)
        )
        return result.scalar_one_or_none()

    async def create_registration_bundle(self, company, shop, branch, user, employee, device):
        self.db.add(company)
        await self.db.flush()

        self.db.add(shop)
        await self.db.flush()

        self.db.add(branch)
        await self.db.flush()

        self.db.add(user)
        self.db.add(employee)
        self.db.add(device)

        await self.db.commit()

        return {
            "company": company,
            "shop": shop,
            "branch": branch,
            "user": user,
            "employee": employee,
            "device": device,
        }
