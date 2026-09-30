"""Shared FastAPI dependencies — the database session and the signed-in user."""

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import User
from app.security.jwt import decode_token

_authenticate_challenge = {"WWW-Authenticate": "Bearer"}

__all__ = ["get_current_user", "get_db", "unauthorized"]


def unauthorized(detail: str) -> HTTPException:
    """A 401 carrying the challenge header, so clients can tell 401 from 403."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=dict(_authenticate_challenge),
    )


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Resolve the `Authorization: Bearer <token>` header to a live `User`.

    Every failure mode is the same 401 — unknown token, expired token, wrong
    signature, user deleted since issue — because telling a caller *why* their
    token was rejected is free reconnaissance.
    """
    if not authorization:
        raise unauthorized("Not authenticated")

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise unauthorized("Not authenticated")

    try:
        payload = decode_token(token.strip())
    except JWTError:
        raise unauthorized("Invalid or expired token") from None

    raw_id = payload.get("sub")
    try:
        user_id = int(raw_id) if raw_id is not None else None
    except (TypeError, ValueError):
        raise unauthorized("Invalid or expired token") from None
    if user_id is None:
        raise unauthorized("Invalid or expired token")

    user = await db.get(User, user_id)
    if user is None:
        raise unauthorized("Invalid or expired token")

    return user
