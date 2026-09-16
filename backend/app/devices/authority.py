import hashlib
import hmac

from fastapi import HTTPException

from app.auth.security import SECRET_KEY


TERMINAL_IDENTITY_REVOKED = "terminal_identity_revoked"
TERMINAL_ASSIGNMENT_CHANGED = "terminal_assignment_changed"
TERMINAL_DECOMMISSIONED = "terminal_decommissioned"


def hash_device_identity(value: str) -> str:
    return hmac.new(
        SECRET_KEY.encode("utf-8"), value.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def terminal_authority_error(status_code: int, code: str, message: str) -> HTTPException:
    """Return a machine-classifiable terminal authority failure.

    Clients must never infer permanent terminal revocation from an HTTP status
    alone. Only these explicit codes are safe to quarantine.
    """

    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )
