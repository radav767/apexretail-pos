from datetime import datetime, timedelta, timezone
UTC = timezone.utc
import bcrypt
from jose import jwt

SECRET_KEY = "CHANGE_THIS_TO_A_LONG_RANDOM_SECRET"
ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60 * 24


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


def create_access_token(user_id: str, email: str):
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_MINUTES)

    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire
    }

    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
