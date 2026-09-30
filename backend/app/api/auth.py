"""
Register, sign in, identify, sign out.

Register and login both answer with a bearer token — registration is
auto sign-in, so an operator who just created an account never has to type
the password they picked a second later.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.security.jwt import create_access_token
from app.security.password import hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

_email_taken = "An account with this email already exists"
_bad_credentials = "Invalid email or password"


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        token=create_access_token(user.id, user.email),
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_email_taken)

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="operator",
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a race with a concurrent registration for the same address.
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_email_taken) from None
    await db.refresh(user)

    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))

    # One failure message for "no such user" and "wrong password": an email
    # address that returns 401-with-a-different-detail is an oracle.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_bad_credentials)

    return _token_response(user)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: User = Depends(get_current_user)) -> Response:
    """Stateless logout: the token is simply dropped by the client."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)
