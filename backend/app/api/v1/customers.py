"""
GET /api/v1/customers  — list customers for the authenticated merchant's business.

Filter rules (query param ?filter=):
  active   : customers whose card last_activity_at is within the last 30 days
  drifting : customers who enrolled more than 14 days ago and either have no
             card or whose card last_activity_at is older than 30 days
  top      : all customers ordered by lifetime_stamps DESC (nulls last)
  (none)   : all customers, ordered by enrolled_at DESC
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.deps import get_current_user
from app.db import get_session
from app.models.customer import Customer
from app.models.loyalty_card import LoyaltyCard, WalletPlatform
from app.models.scan_event import ScanEvent, ScanType
from app.models.user import MerchantUser
from app.schemas.analytics import AnalyticsSummary
from app.schemas.customer import CustomerListItem

router = APIRouter()

ACTIVE_WINDOW_DAYS = 30
DRIFT_ENROLL_DAYS = 14


@router.get("/customers", response_model=List[CustomerListItem])
async def list_customers(
    filter: Optional[str] = Query(default=None, pattern="^(active|drifting|top)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: MerchantUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    business_id = current_user.business_id
    now = datetime.utcnow()
    active_cutoff = now - timedelta(days=ACTIVE_WINDOW_DAYS)
    drift_enroll_cutoff = now - timedelta(days=DRIFT_ENROLL_DAYS)

    # Fetch all customers for this business together with their latest card
    # (one customer may have multiple cards for different programs — we take
    # the one with the most recent last_activity_at as representative)
    customers_result = await session.execute(
        select(Customer).where(Customer.business_id == business_id)
    )
    customers = customers_result.scalars().all()

    # Fetch all loyalty cards for this business indexed by customer_id
    cards_result = await session.execute(
        select(LoyaltyCard).where(LoyaltyCard.business_id == business_id)
    )
    all_cards = cards_result.scalars().all()

    # For each customer pick the card with the most recent last_activity_at
    card_by_customer: dict = {}
    for card in all_cards:
        existing = card_by_customer.get(card.customer_id)
        if existing is None or card.last_activity_at > existing.last_activity_at:
            card_by_customer[card.customer_id] = card

    # Build items
    items: List[CustomerListItem] = []
    for customer in customers:
        card = card_by_customer.get(customer.id)
        item = CustomerListItem(
            customer_id=customer.id,
            name=customer.name,
            contact=customer.contact,
            contact_type=customer.contact_type,
            enrolled_at=customer.enrolled_at,
            enrollment_channel=customer.enrollment_channel,
            current_stamps=card.current_stamps if card else None,
            rewards_available=card.rewards_available if card else None,
            lifetime_stamps=card.lifetime_stamps if card else None,
            last_activity_at=card.last_activity_at if card else None,
            status=card.status if card else None,
        )
        items.append(item)

    # Apply filter
    if filter == "active":
        items = [
            i for i in items
            if i.last_activity_at is not None and i.last_activity_at >= active_cutoff
        ]
    elif filter == "drifting":
        # Drifting: enrolled more than 14 days ago AND (no card OR last_activity_at < 30-day cutoff)
        items = [
            i for i in items
            if i.enrolled_at <= drift_enroll_cutoff
            and (
                i.last_activity_at is None
                or i.last_activity_at < active_cutoff
            )
        ]
    elif filter == "top":
        items.sort(key=lambda i: (i.lifetime_stamps is None, -(i.lifetime_stamps or 0)))
    else:
        items.sort(key=lambda i: i.enrolled_at, reverse=True)

    # Pagination
    return items[offset: offset + limit]


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def analytics_summary(
    current_user: MerchantUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    business_id = current_user.business_id
    now = datetime.utcnow()
    active_cutoff = now - timedelta(days=ACTIVE_WINDOW_DAYS)
    drift_enroll_cutoff = now - timedelta(days=DRIFT_ENROLL_DAYS)

    # total_customers
    total_customers_result = await session.execute(
        select(func.count(Customer.id)).where(Customer.business_id == business_id)
    )
    total_customers: int = total_customers_result.scalar_one()

    # total_cards
    total_cards_result = await session.execute(
        select(func.count(LoyaltyCard.id)).where(LoyaltyCard.business_id == business_id)
    )
    total_cards: int = total_cards_result.scalar_one()

    # total_installs (wallet_platform != 'none')
    total_installs_result = await session.execute(
        select(func.count(LoyaltyCard.id)).where(
            LoyaltyCard.business_id == business_id,
            LoyaltyCard.wallet_platform != WalletPlatform.none,
        )
    )
    total_installs: int = total_installs_result.scalar_one()

    # stamps_issued
    stamps_result = await session.execute(
        select(func.count(ScanEvent.id)).where(
            ScanEvent.business_id == business_id,
            ScanEvent.type == ScanType.stamp,
        )
    )
    stamps_issued: int = stamps_result.scalar_one()

    # rewards_redeemed
    redeems_result = await session.execute(
        select(func.count(ScanEvent.id)).where(
            ScanEvent.business_id == business_id,
            ScanEvent.type == ScanType.redeem,
        )
    )
    rewards_redeemed: int = redeems_result.scalar_one()

    # Active / drifting — need per-customer latest card activity
    customers_result = await session.execute(
        select(Customer).where(Customer.business_id == business_id)
    )
    customers = customers_result.scalars().all()

    cards_result = await session.execute(
        select(LoyaltyCard).where(LoyaltyCard.business_id == business_id)
    )
    all_cards = cards_result.scalars().all()

    card_by_customer: dict = {}
    for card in all_cards:
        existing = card_by_customer.get(card.customer_id)
        if existing is None or card.last_activity_at > existing.last_activity_at:
            card_by_customer[card.customer_id] = card

    active_count = 0
    drifting_count = 0
    for customer in customers:
        card = card_by_customer.get(customer.id)
        last_activity = card.last_activity_at if card else None
        if last_activity is not None and last_activity >= active_cutoff:
            active_count += 1
        elif customer.enrolled_at <= drift_enroll_cutoff and (
            last_activity is None or last_activity < active_cutoff
        ):
            drifting_count += 1

    # channel_breakdown
    channels_result = await session.execute(
        select(Customer.enrollment_channel, func.count(Customer.id))
        .where(Customer.business_id == business_id)
        .group_by(Customer.enrollment_channel)
    )
    channel_breakdown = {row[0]: row[1] for row in channels_result.all()}

    return AnalyticsSummary(
        total_customers=total_customers,
        total_cards=total_cards,
        total_installs=total_installs,
        stamps_issued=stamps_issued,
        rewards_redeemed=rewards_redeemed,
        active_customers=active_count,
        drifting_customers=drifting_count,
        channel_breakdown=channel_breakdown,
    )
