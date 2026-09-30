"""
HS256 access tokens.

Stateless on purpose: there is no server-side session store to invalidate
against, so logout is advisory and the token simply expires. `sub` carries the
user id because that is what every request resolves to a `User` row from.
"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import get_settings

__all__ = ["create_access_token", "decode_token", "JWTError"]


def create_access_token(user_id: int, email: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=settings.AURORA_JWT_EXPIRY_DAYS)).timestamp()),
    }
    return jwt.encode(payload, settings.AURORA_JWT_SECRET, algorithm="HS256")


def decode_token(token: str) -> dict:
    """Return the payload, raising `JWTError` for anything untrusted."""
    return jwt.decode(token, get_settings().AURORA_JWT_SECRET, algorithms=["HS256"])
