from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.deps import get_current_user
from app.db import get_session
from app.models.program import RewardProgram
from app.models.user import MerchantUser
from app.schemas.program import ProgramCreate, ProgramRead, ProgramUpdate

router = APIRouter()


@router.post("", response_model=ProgramRead, status_code=status.HTTP_201_CREATED)
async def create_program(
    body: ProgramCreate,
    current_user: MerchantUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    program = RewardProgram(
        business_id=current_user.business_id,
        name=body.name,
        type=body.type,
        stamps_required=body.stamps_required,
        reward_description=body.reward_description,
        active=body.active,
    )
    session.add(program)
    await session.commit()
    await session.refresh(program)
    return program


@router.get("", response_model=List[ProgramRead])
async def list_programs(
    current_user: MerchantUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(RewardProgram).where(RewardProgram.business_id == current_user.business_id)
    )
    return result.scalars().all()


@router.get("/{program_id}", response_model=ProgramRead)
async def get_program(
    program_id: int,
    current_user: MerchantUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(RewardProgram).where(
            RewardProgram.id == program_id,
            RewardProgram.business_id == current_user.business_id,
        )
    )
    program = result.scalar_one_or_none()
    if not program:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")
    return program


@router.patch("/{program_id}", response_model=ProgramRead)
async def update_program(
    program_id: int,
    body: ProgramUpdate,
    current_user: MerchantUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(RewardProgram).where(
            RewardProgram.id == program_id,
            RewardProgram.business_id == current_user.business_id,
        )
    )
    program = result.scalar_one_or_none()
    if not program:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(program, field, value)

    session.add(program)
    await session.commit()
    await session.refresh(program)
    return program
