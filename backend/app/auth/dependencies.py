from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import decode_access_token, hash_session_token
from app.core.config import get_settings
from app.db.session import get_db
from app.employees.service import EmployeeService
from app.models import Employee, User, PosSession
from datetime import datetime, timezone, timedelta
from app.subscriptions.service import SubscriptionService


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthActor:
    actor_type: str
    company_id: UUID
    role: str
    user: User | None = None
    employee: Employee | None = None
    permissions: dict[str, bool] | None = None


async def get_auth_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: AsyncSession = Depends(get_db),
) -> AuthActor:
    if credentials is None:
        raise HTTPException(401, "Authentication required")

    actor = await resolve_auth_actor(
        credentials.credentials,
        db,
    )

    if actor is None:
        raise HTTPException(401, "Invalid access token")

    return actor


async def get_optional_auth_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(
        bearer_scheme
    ),
    db: AsyncSession = Depends(get_db),
) -> AuthActor | None:
    if credentials is None:
        return None

    actor = await resolve_auth_actor(
        credentials.credentials,
        db,
    )

    if actor is None:
        raise HTTPException(401, "Invalid access token")

    return actor


async def resolve_auth_actor(
    token: str,
    db: AsyncSession,
) -> AuthActor | None:
    if not token:
        return None

    session_result = await db.execute(select(PosSession).where(PosSession.token_hash == hash_session_token(token), PosSession.revoked_at.is_(None), PosSession.expires_at > datetime.now(timezone.utc)))
    session = session_result.scalar_one_or_none()
    if session:
        result = await db.execute(select(Employee).where(Employee.id == session.employee_id, Employee.active == True, Employee.deleted == False))
        employee = result.scalar_one_or_none()
        if not employee:
            session.revoked_at = datetime.now(timezone.utc); session.revoke_reason = "employee_inactive"; await db.commit(); return None
        session.last_authenticated_at = datetime.now(timezone.utc)
        session.expires_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(hours=12)
        actor = AuthActor(
            actor_type="employee",
            company_id=employee.company_id,
            role=employee.role,
            employee=employee,
            permissions=EmployeeService.build_permissions(
                employee.role,
                employee.permissions,
            ),
        )
        await db.commit()
        return actor

    try:
        payload = decode_access_token(token)
    except JWTError:
        return None

    token_type = str(
        payload.get("token_type") or "user"
    ).strip()
    subject = payload.get("sub")

    if not subject:
        return None

    try:
        subject_id = UUID(str(subject))
    except ValueError:
        return None

    if token_type == "employee":
        company_id = payload.get("company_id")

        if not company_id:
            return None

        try:
            company_uuid = UUID(str(company_id))
        except ValueError:
            return None

        result = await db.execute(
            select(Employee).where(
                Employee.id == subject_id,
                Employee.company_id == company_uuid,
                Employee.active == True,
                Employee.deleted == False,
            )
        )
        employee = result.scalar_one_or_none()

        if not employee:
            raise HTTPException(
                401,
                "Employee session is no longer valid",
            )

        permissions = EmployeeService.build_permissions(
            employee.role,
            employee.permissions,
        )

        return AuthActor(
            actor_type="employee",
            company_id=employee.company_id,
            role=employee.role,
            employee=employee,
            permissions=permissions,
        )

    result = await db.execute(
        select(User).where(
            User.id == subject_id,
            User.active == True,
            User.deleted == False,
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            401,
            "User session is no longer valid",
        )

    return AuthActor(
        actor_type="user",
        company_id=user.company_id,
        role=user.role,
        user=user,
        permissions=None,
    )


def ensure_company_access(
    actor: AuthActor,
    company_id: UUID,
):
    if actor.company_id != company_id:
        raise HTTPException(403, "Forbidden")


def require_permission(permission_key: str):
    async def dependency(
        actor: AuthActor = Depends(get_auth_actor),
    ) -> AuthActor:
        if actor.actor_type == "user":
            return actor

        if actor.role in {"owner", "administrator"}:
            return actor

        if actor.permissions and actor.permissions.get(permission_key):
            return actor

        raise HTTPException(403, "Permission denied")

    return dependency


def require_body_permission(permission_key: str):
    async def dependency(
        request: Request,
        actor: AuthActor = Depends(
            require_permission(permission_key)
        ),
    ) -> AuthActor:
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid request body")

        company_id = (
            payload.get("company_id")
            if isinstance(payload, dict)
            else None
        )

        if not company_id:
            raise HTTPException(400, "company_id is required")

        try:
            company_uuid = UUID(str(company_id))
        except ValueError:
            raise HTTPException(400, "Invalid company_id")

        ensure_company_access(actor, company_uuid)
        return actor

    return dependency


def require_path_permission(permission_key: str):
    async def dependency(
        request: Request,
        actor: AuthActor = Depends(
            require_permission(permission_key)
        ),
    ) -> AuthActor:
        company_id = request.path_params.get("company_id")

        if not company_id:
            raise HTTPException(400, "company_id is required")

        try:
            company_uuid = UUID(str(company_id))
        except ValueError:
            raise HTTPException(400, "Invalid company_id")

        ensure_company_access(actor, company_uuid)
        return actor

    return dependency


def require_owner(actor: AuthActor):
    if actor.actor_type == "user":
        return actor
    if actor.role == "owner":
        return actor
    raise HTTPException(403, "Owner access required")


async def require_body_owner(
    request: Request,
    actor: AuthActor = Depends(get_auth_actor),
):
    require_owner(actor)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid request body")
    company_id = payload.get("company_id") if isinstance(payload, dict) else None
    if not company_id:
        raise HTTPException(400, "company_id is required")
    ensure_company_access(actor, UUID(str(company_id)))
    return actor


async def require_path_owner(
    request: Request,
    actor: AuthActor = Depends(get_auth_actor),
):
    require_owner(actor)
    company_id = request.path_params.get("company_id")
    if not company_id:
        raise HTTPException(400, "company_id is required")
    ensure_company_access(actor, UUID(str(company_id)))
    return actor


async def require_billable_body_company(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid request body")
    company_id = payload.get("company_id") if isinstance(payload, dict) else None
    if not company_id:
        raise HTTPException(400, "company_id is required")
    service = SubscriptionService(
        db,
        offline_grace_hours=get_settings().subscription_offline_grace_hours,
        provider_name=get_settings().subscription_provider_name,
    )
    await service.enforce_writes_allowed(UUID(str(company_id)))


async def require_billable_path_company(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    company_id = request.path_params.get("company_id")
    if not company_id:
        raise HTTPException(400, "company_id is required")
    service = SubscriptionService(
        db,
        offline_grace_hours=get_settings().subscription_offline_grace_hours,
        provider_name=get_settings().subscription_provider_name,
    )
    await service.enforce_writes_allowed(UUID(str(company_id)))
