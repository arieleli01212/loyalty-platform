import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
    verify_password,
)
from app.db import get_session
from app.models.business import Business
from app.models.user import MerchantUser, UserRole
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)

router = APIRouter()


def slugify(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    # Check if email is already taken
    result = await session.execute(select(MerchantUser).where(MerchantUser.email == body.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create user first (without business_id)
    user = MerchantUser(
        email=body.email,
        hashed_password=get_password_hash(body.password),
        role=UserRole.owner,
        business_id=None,
    )
    session.add(user)
    await session.flush()  # get user.id

    # Create slug, ensure uniqueness
    base_slug = slugify(body.business_name)
    if not base_slug:
        base_slug = "business"

    slug = base_slug
    result = await session.execute(select(Business).where(Business.slug == slug))
    if result.scalar_one_or_none():
        slug = f"{base_slug}-{secrets.token_hex(4)}"

    # Create business
    business = Business(
        name=body.business_name,
        slug=slug,
        owner_user_id=user.id,
    )
    session.add(business)
    await session.flush()  # get business.id

    # Update user with business_id
    user.business_id = business.id
    session.add(user)

    await session.commit()
    await session.refresh(user)

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(MerchantUser).where(MerchantUser.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)):
    user_id_str = decode_refresh_token(body.refresh_token)
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    try:
        user_id = int(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    result = await session.execute(select(MerchantUser).where(MerchantUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    access_token = create_access_token(user.id)
    return AccessTokenResponse(access_token=access_token, token_type="bearer")
