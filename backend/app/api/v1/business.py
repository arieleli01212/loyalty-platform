from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.deps import get_current_user, get_owner_user
from app.core.security import get_password_hash
from app.db import get_session
from app.models.business import Business
from app.models.user import MerchantUser, UserRole
from app.schemas.business import BusinessRead, BusinessUpdate, StaffCreate, StaffOut

router = APIRouter()


@router.get("", response_model=BusinessRead)
async def get_business(
    current_user: MerchantUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Business).where(Business.id == current_user.business_id)
    )
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    return business


@router.patch("", response_model=BusinessRead)
async def update_business(
    body: BusinessUpdate,
    current_user: MerchantUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Business).where(Business.id == current_user.business_id)
    )
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(business, field, value)

    session.add(business)
    await session.commit()
    await session.refresh(business)
    return business


@router.get("/staff", response_model=list[StaffOut])
async def list_staff(
    current_user: MerchantUser = Depends(get_owner_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(MerchantUser).where(
            MerchantUser.business_id == current_user.business_id,
            MerchantUser.role == UserRole.staff,
        )
    )
    return result.scalars().all()


@router.post("/staff", response_model=StaffOut, status_code=status.HTTP_201_CREATED)
async def create_staff(
    body: StaffCreate,
    current_user: MerchantUser = Depends(get_owner_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(MerchantUser).where(MerchantUser.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    staff = MerchantUser(
        email=body.email,
        hashed_password=get_password_hash(body.password),
        role=UserRole.staff,
        business_id=current_user.business_id,
    )
    session.add(staff)
    await session.commit()
    await session.refresh(staff)
    return staff


@router.delete("/staff/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_staff(
    user_id: int,
    current_user: MerchantUser = Depends(get_owner_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(MerchantUser).where(
            MerchantUser.id == user_id,
            MerchantUser.business_id == current_user.business_id,
            MerchantUser.role == UserRole.staff,
        )
    )
    staff = result.scalar_one_or_none()
    if not staff:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found")
    await session.delete(staff)
    await session.commit()
