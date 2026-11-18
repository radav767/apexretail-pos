from datetime import datetime, timedelta, timezone
import logging

import bcrypt
import hashlib, secrets
import jwt
from jwt import PyJWTError as JWTError

from app.auth.entitlement_keys import (
    EntitlementKeyConfigurationError,
    load_public_keyring,
    load_signing_key,
    safe_kid,
)
from app.core.config import get_settings, validate_jwt_secret

# Legacy terminal identity hashing depends on these exact bytes. This constant
# is not an authentication signing fallback; changing it needs a data plan.
SECRET_KEY = "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET"
ACCESS_TOKEN_MINUTES = 60 * 24
EMPLOYEE_ACCESS_TOKEN_MINUTES = 60 * 24 * 30
OFFLINE_SHIFT_TOKEN_MINUTES = 60 * 24 * 30
ENTITLEMENT_SNAPSHOT_MINUTES = 60 * 24
UTC = timezone.utc
ENTITLEMENT_ISSUER = "apexpos"
ENTITLEMENT_AUDIENCE = "apexpos-pos-entitlement"
ENTITLEMENT_ALLOWED_STATUSES = {"trial", "active", "grace_period"}
logger = logging.getLogger(__name__)


class EntitlementVerificationError(JWTError):
    def __init__(self, category: str, kid: str | None = None):
        self.category = category
        self.kid = safe_kid(kid)
        super().__init__(f"Entitlement verification failed: {category}")


def _verification_failure(category: str, kid: object = None):
    safe_key_id = safe_kid(kid)
    logger.warning(
        "entitlement_verification_failed category=%s kid=%s",
        category,
        safe_key_id or "none",
    )
    raise EntitlementVerificationError(category, safe_key_id)


def _aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return value.astimezone(UTC)


def _claim_timestamp(value: object, field: str, kid: str | None) -> datetime:
    try:
        return datetime.fromtimestamp(float(value), UTC)
    except (TypeError, ValueError, OverflowError):
        _verification_failure(f"invalid_{field}", kid)


def _claim_datetime(value: object, field: str, kid: str | None) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        _verification_failure(f"invalid_{field}", kid)
    if parsed.tzinfo is None:
        _verification_failure(f"invalid_{field}", kid)
    return parsed.astimezone(UTC)


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
        validate_jwt_secret(settings.jwt_secret, settings.jwt_algorithm),
        algorithm=settings.jwt_algorithm,
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


def create_offline_shift_token(
    *, shift_id: str, company_id: str, branch_id: str,
    device_id: str, employee_id: str, opened_at: str,
) -> str:
    """Sign the immutable cashier/register identity used by queued sales."""
    return _create_token(
        {
            "sub": shift_id,
            "shift_id": shift_id,
            "company_id": company_id,
            "branch_id": branch_id,
            "device_id": device_id,
            "employee_id": employee_id,
            "opened_at": opened_at,
            "token_type": "offline_shift",
        },
        OFFLINE_SHIFT_TOKEN_MINUTES,
    )


def decode_offline_shift_token(token: str, *, verify_expiration: bool = True) -> dict:
    settings = get_settings()
    payload = jwt.decode(
        token,
        validate_jwt_secret(settings.jwt_secret, settings.jwt_algorithm),
        algorithms=[settings.jwt_algorithm],
        options={"verify_exp": verify_expiration},
    )
    if payload.get("token_type") != "offline_shift":
        raise ValueError("Invalid offline shift token type")
    return payload


def create_entitlement_snapshot_token(
    *,
    company_id: str,
    status: str,
    plan: str | None,
    offline_grace_expires_at: datetime,
    snapshot_expires_at: datetime | None = None,
    issued_at: datetime | None = None,
    features: dict | None = None,
    limits: dict | None = None,
) -> str:
    settings = get_settings()
    algorithm = str(settings.entitlement_signing_algorithm or "").upper()
    if algorithm != "RS256":
        raise EntitlementKeyConfigurationError(
            "Entitlement snapshots must use RS256"
        )
    keyring = load_public_keyring(settings)
    active_kid = safe_kid(settings.entitlement_active_key_id)
    if not active_kid or active_kid not in keyring.keys:
        raise EntitlementKeyConfigurationError(
            "ENTITLEMENT_ACTIVE_KEY_ID must identify a configured public key"
        )
    now = _aware_utc(issued_at or datetime.now(UTC), "issued_at")
    active_key = keyring.keys[active_kid]
    if active_key.accept_until and now > active_key.accept_until:
        raise EntitlementKeyConfigurationError(
            "The active entitlement signing key has reached its acceptance deadline"
        )
    signing_key = load_signing_key(settings)
    expiry = (
        snapshot_expires_at
        or (now + timedelta(minutes=ENTITLEMENT_SNAPSHOT_MINUTES))
    )
    expiry = _aware_utc(expiry, "snapshot_expires_at")
    grace = _aware_utc(offline_grace_expires_at, "offline_grace_expires_at")
    if expiry <= now or expiry > now + timedelta(
        seconds=keyring.max_token_lifetime_seconds
    ):
        raise ValueError("Snapshot expiry exceeds the trusted maximum lifetime")
    if grace <= now or grace > now + timedelta(
        seconds=keyring.max_offline_grace_seconds
    ):
        raise ValueError("Offline grace exceeds the trusted maximum lifetime")

    token = jwt.encode(
        {
            "sub": str(company_id),
            "company_id": str(company_id),
            "status": status,
            "plan": plan,
            "offline_grace_expires_at": grace.isoformat(),
            "token_type": "entitlement",
            "iat": int(now.timestamp()),
            "exp": int(expiry.timestamp()),
            "iss": ENTITLEMENT_ISSUER,
            "aud": ENTITLEMENT_AUDIENCE,
            **({"features":features,"limits":limits} if features is not None else {}),
        },
        signing_key,
        algorithm="RS256",
        headers={"kid": active_kid, "typ": "JWT"},
    )
    try:
        jwt.decode(
            token,
            active_key.public_key_pem,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_exp": False, "verify_iat": False},
        )
    except JWTError as exc:
        raise EntitlementKeyConfigurationError(
            "Active signing key does not match its configured public key"
        ) from exc
    logger.info("entitlement_snapshot_issued kid=%s", active_kid)
    return token


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token,
        validate_jwt_secret(settings.jwt_secret, settings.jwt_algorithm),
        algorithms=[settings.jwt_algorithm],
    )


def decode_entitlement_token(
    token: str,
    *,
    expected_company_id: str,
    now: datetime | None = None,
) -> dict:
    settings = get_settings()
    if str(settings.entitlement_signing_algorithm or "").upper() != "RS256":
        raise EntitlementKeyConfigurationError(
            "Entitlement snapshots must use RS256"
        )
    keyring = load_public_keyring(settings)
    current_time = _aware_utc(now or datetime.now(UTC), "now")
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        _verification_failure("malformed_token")

    if header.get("alg") != "RS256":
        _verification_failure("algorithm_mismatch", header.get("kid"))
    if header.get("typ") != "JWT":
        _verification_failure("type_mismatch", header.get("kid"))

    raw_kid = header.get("kid")
    legacy = raw_kid in (None, "")
    if legacy:
        kid = keyring.legacy_key_id
        if not kid or not keyring.legacy_accept_until:
            _verification_failure("legacy_not_configured")
        if current_time > keyring.legacy_accept_until:
            _verification_failure("legacy_key_retired", kid)
    else:
        kid = safe_kid(raw_kid)
        if not kid:
            _verification_failure("invalid_key_id")

    verification_key = keyring.keys.get(kid)
    if verification_key is None:
        _verification_failure("unknown_key_id", kid)
    if verification_key.accept_until and current_time > verification_key.accept_until:
        _verification_failure("key_retired", kid)

    try:
        claims = jwt.decode(
            token,
            verification_key.public_key_pem,
            algorithms=["RS256"],
            options={"verify_aud": False, "verify_exp": False, "verify_iat": False},
        )
    except JWTError:
        _verification_failure("invalid_signature", kid)

    if claims.get("token_type") != "entitlement":
        _verification_failure("invalid_token_type", kid)
    company_id = str(claims.get("company_id") or "")
    if (
        not company_id
        or company_id != str(expected_company_id)
        or str(claims.get("sub") or "") != company_id
    ):
        _verification_failure("company_mismatch", kid)
    if claims.get("status") not in ENTITLEMENT_ALLOWED_STATUSES:
        _verification_failure("subscription_not_writable", kid)

    expiry = _claim_timestamp(claims.get("exp"), "expiry", kid)
    grace = _claim_datetime(
        claims.get("offline_grace_expires_at"), "offline_grace", kid
    )
    if current_time > expiry:
        _verification_failure("snapshot_expired", kid)
    if current_time > grace:
        _verification_failure("offline_grace_expired", kid)

    if legacy:
        # Existing no-kid tokens have no trusted issuance timestamp. Their hard
        # authorization ceiling is the operator-configured legacy deadline.
        if current_time > keyring.legacy_accept_until:
            _verification_failure("legacy_key_retired", kid)
    else:
        issued_at = _claim_timestamp(claims.get("iat"), "issued_at", kid)
        if issued_at > current_time + timedelta(seconds=60):
            _verification_failure("issued_in_future", kid)
        if expiry <= issued_at or (
            expiry - issued_at
        ).total_seconds() > keyring.max_token_lifetime_seconds:
            _verification_failure("token_lifetime_exceeded", kid)
        if grace <= issued_at or (
            grace - issued_at
        ).total_seconds() > keyring.max_offline_grace_seconds:
            _verification_failure("offline_grace_exceeded", kid)
        if claims.get("iss") != ENTITLEMENT_ISSUER:
            _verification_failure("issuer_mismatch", kid)
        if claims.get("aud") != ENTITLEMENT_AUDIENCE:
            _verification_failure("audience_mismatch", kid)

    logger.info("entitlement_verified kid=%s legacy=%s", kid, legacy)
    return claims
