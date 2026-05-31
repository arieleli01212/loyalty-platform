from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.models.loyalty_card import LoyaltyCard, CardStatus
from app.models.program import RewardProgram
from app.models.scan_event import ScanEvent, ScanType, ScanSource
from app.models.user import MerchantUser
from app.services.wallet.stub import StubWalletProvider
from app.schemas.scan import ScanResponse


stub_wallet = StubWalletProvider()


async def process_scan(
    barcode_token: str,
    action: ScanType,
    current_user: MerchantUser,
    session: AsyncSession,
    idempotency_key: Optional[str] = None,
) -> ScanResponse:
    # Resolve LoyaltyCard by barcode_token
    result = await session.execute(
        select(LoyaltyCard).where(LoyaltyCard.barcode_token == barcode_token)
    )
    card = result.scalar_one_or_none()

    if not card:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found")

    # Verify card belongs to the same business as the staff user
    if card.business_id != current_user.business_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Card does not belong to your business",
        )

    # Check card status
    if card.status != CardStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Card is {card.status.value}",
        )

    # Load RewardProgram
    result = await session.execute(
        select(RewardProgram).where(RewardProgram.id == card.program_id)
    )
    program = result.scalar_one_or_none()
    if not program:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Program not found")

    if not program.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Program is not active",
        )

    # Idempotency check
    if idempotency_key:
        result = await session.execute(
            select(ScanEvent).where(ScanEvent.idempotency_key == idempotency_key)
        )
        existing_event = result.scalar_one_or_none()
        if existing_event:
            # Return the current state of the card without processing again
            return ScanResponse(
                card_id=card.id,
                current_stamps=card.current_stamps,
                rewards_available=card.rewards_available,
                lifetime_stamps=card.lifetime_stamps,
                action=action.value,
                message="Already processed (idempotent)",
            )

    # Throttle check for stamp actions
    if action == ScanType.stamp:
        throttle_window = datetime.utcnow() - timedelta(minutes=settings.STAMP_THROTTLE_MINUTES)
        result = await session.execute(
            select(ScanEvent).where(
                ScanEvent.card_id == card.id,
                ScanEvent.type == ScanType.stamp,
                ScanEvent.created_at >= throttle_window,
            )
        )
        recent_stamp = result.scalar_one_or_none()
        if recent_stamp:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Stamp throttled: please wait {settings.STAMP_THROTTLE_MINUTES} minutes between stamps",
            )

    # Process action
    if action == ScanType.stamp:
        card.current_stamps += 1
        card.lifetime_stamps += 1

        if card.current_stamps >= program.stamps_required:
            card.rewards_available += 1
            card.current_stamps = 0
            message = f"Reward earned! {card.rewards_available} reward(s) available."
        else:
            remaining = program.stamps_required - card.current_stamps
            message = f"Stamp added! {card.current_stamps}/{program.stamps_required} stamps. {remaining} more needed."

    elif action == ScanType.redeem:
        if card.rewards_available == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No rewards available to redeem",
            )
        card.rewards_available -= 1
        message = f"Reward redeemed! {card.rewards_available} reward(s) remaining."

    # Update last_activity_at
    card.last_activity_at = datetime.utcnow()
    session.add(card)

    # Create ScanEvent
    scan_event = ScanEvent(
        card_id=card.id,
        business_id=current_user.business_id,
        staff_user_id=current_user.id,
        type=action,
        source=ScanSource.scanner,
        idempotency_key=idempotency_key,
    )
    session.add(scan_event)

    await session.commit()
    await session.refresh(card)

    # Call wallet provider (no-op for stub)
    stub_wallet.update_pass(card)

    return ScanResponse(
        card_id=card.id,
        current_stamps=card.current_stamps,
        rewards_available=card.rewards_available,
        lifetime_stamps=card.lifetime_stamps,
        action=action.value,
        message=message,
    )
