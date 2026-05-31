from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.deps import get_current_user
from app.db import get_session
from app.models.business import Business
from app.models.user import MerchantUser
from app.schemas.business import BusinessRead, BusinessUpdate

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
