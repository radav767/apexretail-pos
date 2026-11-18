from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.auth.schema import RegisterRequest, LoginRequest
from app.auth.repository import AuthRepository
from app.auth.service import AuthService
from app.auth.registration_currencies import serialize_registration_currencies
from app.auth.dependencies import AuthActor, get_auth_actor
from app.auth.sessions import revoke_user_sessions

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/registration-currencies")
async def registration_currencies():
    return {"items": serialize_registration_currencies()}


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


@router.post('/logout-all')
async def logout_all(actor: AuthActor = Depends(get_auth_actor), db: AsyncSession = Depends(get_db)):
    await revoke_user_sessions(db, actor)
    return {'ok': True, 'scope': 'all_user_sessions'}


@router.get("/test")
async def auth_test():
    return {"ok": True, "message": "ApexRetail POS Auth ready"}
