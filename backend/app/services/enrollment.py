"""Shared enrollment helper — idempotent customer + loyalty card creation."""

import logging
import uuid
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.business import Business
from app.models.customer import Customer
from app.models.loyalty_card import LoyaltyCard, WalletPlatform, CardStatus
from app.models.program import RewardProgram
from app.schemas.enrollment import EnrollResponse
from app.services.wallet.stub import StubWalletProvider

logger = logging.getLogger(__name__)

_wallet_provider = StubWalletProvider()


async def find_or_create_enrollment(
    business: Business,
    program: RewardProgram,
    *,
    email: str,
    name: str,
    google_sub: Optional[str],
    channel: str,
    session: AsyncSession,
) -> EnrollResponse:
    """Idempotent enrollment.

    If a customer already exists at (business, email), return their existing
    card. Otherwise create both customer and card.

    Always marks email_verified=True — callers must have already verified the
    email (either via OTP or Google OAuth).

    Race safety: the unique index on (business_id, email) is the DB-level
    safety net. If two concurrent requests slip past the SELECT together, one
    INSERT will hit IntegrityError; we catch that and re-fetch the existing row
    rather than returning an error to the user.
    """
    # --- look up existing customer ---
    result = await session.execute(
        select(Customer).where(
            Customer.business_id == business.id,
            Customer.email == email,
        )
    )
    customer = result.scalar_one_or_none()

    if customer is not None:
        # Backfill google_sub if we now have one and they didn't previously.
        changed = False
        if google_sub and not customer.google_sub:
            customer.google_sub = google_sub
            changed = True
        if not customer.email_verified:
            customer.email_verified = True
            changed = True
        if changed:
            session.add(customer)
            await session.flush()

        # Find or create the loyalty card for this program.
        card_result = await session.execute(
            select(LoyaltyCard).where(
                LoyaltyCard.customer_id == customer.id,
                LoyaltyCard.program_id == program.id,
            )
        )
        card = card_result.scalar_one_or_none()
        if card is None:
            card = _create_card(business, customer, program)
            session.add(card)
            await session.flush()
            await session.refresh(card)
        await session.commit()
    else:
        # --- create new customer + card ---
        customer = Customer(
            business_id=business.id,
            name=name,
            email=email,
            email_verified=True,
            google_sub=google_sub,
            enrollment_channel=channel,
        )
        session.add(customer)
        try:
            await session.flush()
        except IntegrityError:
            # Race: another request inserted this (business_id, email) first.
            await session.rollback()
            result = await session.execute(
                select(Customer).where(
                    Customer.business_id == business.id,
                    Customer.email == email,
                )
            )
            customer = result.scalar_one()
            if google_sub and not customer.google_sub:
                customer.google_sub = google_sub
                session.add(customer)
                await session.flush()

        card_result = await session.execute(
            select(LoyaltyCard).where(
                LoyaltyCard.customer_id == customer.id,
                LoyaltyCard.program_id == program.id,
            )
        )
        card = card_result.scalar_one_or_none()
        if card is None:
            card = _create_card(business, customer, program)
            session.add(card)
            await session.flush()
            await session.refresh(card)

        await session.commit()

    await session.refresh(customer)
    await session.refresh(card)

    artifact = _wallet_provider.create_pass(card)

    return EnrollResponse(
        customer_id=customer.id,
        card_id=card.id,
        pass_serial=card.pass_serial,
        pass_url=artifact.url,
        current_stamps=card.current_stamps,
        stamps_required=program.stamps_required,
        reward_description=program.reward_description,
        email=customer.email,
        email_verified=customer.email_verified,
    )


def _create_card(
    business: Business,
    customer: Customer,
    program: RewardProgram,
) -> LoyaltyCard:
    return LoyaltyCard(
        business_id=business.id,
        customer_id=customer.id,
        program_id=program.id,
        pass_serial=str(uuid.uuid4()),
        wallet_platform=WalletPlatform.stub,
        current_stamps=0,
        status=CardStatus.active,
    )
