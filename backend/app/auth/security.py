from datetime import datetime, timedelta, timezone

import bcrypt
import hashlib, secrets
from jose import jwt

from app.core.config import get_settings

SECRET_KEY = "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET"
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60 * 24
EMPLOYEE_ACCESS_TOKEN_MINUTES = 60 * 24 * 30
ENTITLEMENT_SNAPSHOT_MINUTES = 60 * 24
UTC = timezone.utc


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        password.encode("utf-8"),
        password_hash.encode("utf-8")
    )

def create_session_token() -> str:
    return secrets.token_urlsafe(32)

def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_token(payload: dict, expires_in_minutes: int) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(
        minutes=expires_in_minutes
    )
    token_payload = {
        **payload,
        "exp": expire,
    }
    return jwt.encode(
        token_payload,
        settings.jwt_secret or SECRET_KEY,
        algorithm=settings.jwt_algorithm or ALGORITHM,
    )


def create_access_token(
    user_id: str,
    email: str,
) -> str:
    return _create_token(
        {
            "sub": user_id,
            "email": email,
            "token_type": "user",
        },
        ACCESS_TOKEN_MINUTES,
    )


def create_employee_access_token(
    *,
    employee_id: str,
    company_id: str,
    role: str,
) -> str:
    return _create_token(
        {
            "sub": employee_id,
            "company_id": company_id,
            "role": role,
            "token_type": "employee",
        },
        EMPLOYEE_ACCESS_TOKEN_MINUTES,
    )


def create_entitlement_snapshot_token(
    *,
    company_id: str,
    status: str,
    plan: str | None,
    offline_grace_expires_at: datetime,
    snapshot_expires_at: datetime | None = None,
) -> str:
    settings = get_settings()
    algorithm = settings.entitlement_signing_algorithm
    signing_key = (
        settings.entitlement_private_key
        if algorithm.upper().startswith(("RS", "ES"))
        else settings.jwt_secret
    )
    if not signing_key:
        raise RuntimeError(
            "Entitlement signing key is not configured"
        )
    expiry = (
        snapshot_expires_at
        or (
            datetime.now(UTC)
            + timedelta(minutes=ENTITLEMENT_SNAPSHOT_MINUTES)
        )
    )
    return jwt.encode(
        {
            "sub": company_id,
            "company_id": company_id,
            "status": status,
            "plan": plan,
            "offline_grace_expires_at": offline_grace_expires_at.isoformat(),
            "token_type": "entitlement",
            "exp": expiry,
        },
        signing_key,
        algorithm=algorithm,
    )


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret or SECRET_KEY,
        algorithms=[settings.jwt_algorithm or ALGORITHM],
    )


def decode_entitlement_token(token: str) -> dict:
    settings = get_settings()
    algorithm = settings.entitlement_signing_algorithm
    verification_key = (
        settings.entitlement_public_key
        if algorithm.upper().startswith(("RS", "ES"))
        else settings.jwt_secret
    )
    if not verification_key:
        raise RuntimeError(
            "Entitlement verification key is not configured"
        )
    return jwt.decode(
        token,
        verification_key,
        algorithms=[algorithm],
    )
