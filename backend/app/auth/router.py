from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.schema import RegisterRequest, LoginRequest
from app.auth.repository import AuthRepository
from app.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register")
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    repo = AuthRepository(db)
    service = AuthService(repo)
    return await service.register(data)


@router.post("/login")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    repo = AuthRepository(db)
    service = AuthService(repo)
    return await service.login(data)


@router.get("/test")
async def auth_test():
    return {"ok": True, "message": "ApexRetail POS Auth ready"}
