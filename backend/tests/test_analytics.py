"""
Tests for:
  GET /api/v1/customers
  GET /api/v1/analytics/summary
"""
import secrets
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import select

from app.models.customer import Customer
from app.models.loyalty_card import LoyaltyCard, WalletPlatform, CardStatus
from app.models.scan_event import ScanEvent, ScanType, ScanSource
from app.models.user import MerchantUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_business_id(test_session, email: str) -> int:
    result = await test_session.execute(
        select(MerchantUser).where(MerchantUser.email == email)
    )
    user = result.scalar_one()
    return user.business_id


async def _create_customer(
    test_session,
    business_id: int,
    *,
    name: str = "Test Customer",
    email: str | None = None,
    enrollment_channel: str = "web",
    enrolled_at: datetime | None = None,
) -> Customer:
    customer = Customer(
        business_id=business_id,
        name=name,
        email=email or f"cust-{secrets.token_hex(4)}@example.com",
        email_verified=True,
        enrolled_at=enrolled_at or datetime.utcnow(),
        enrollment_channel=enrollment_channel,
    )
    test_session.add(customer)
    await test_session.flush()
    return customer


async def _create_card(
    test_session,
    business_id: int,
    customer_id: int,
    program_id: int,
    *,
    wallet_platform: WalletPlatform = WalletPlatform.stub,
    last_activity_at: datetime | None = None,
    current_stamps: int = 0,
    lifetime_stamps: int = 0,
    rewards_available: int = 0,
) -> LoyaltyCard:
    card = LoyaltyCard(
        business_id=business_id,
        customer_id=customer_id,
        program_id=program_id,
        barcode_token=secrets.token_urlsafe(32),
        pass_serial=str(uuid.uuid4()),
        wallet_platform=wallet_platform,
        status=CardStatus.active,
        current_stamps=current_stamps,
        lifetime_stamps=lifetime_stamps,
        rewards_available=rewards_available,
    )
    if last_activity_at is not None:
        card.last_activity_at = last_activity_at
    test_session.add(card)
    await test_session.flush()
    return card


async def _create_scan_event(
    test_session,
    card_id: int,
    business_id: int,
    staff_user_id: int,
    scan_type: ScanType,
) -> ScanEvent:
    event = ScanEvent(
        card_id=card_id,
        business_id=business_id,
        staff_user_id=staff_user_id,
        type=scan_type,
        source=ScanSource.manual,
    )
    test_session.add(event)
    await test_session.flush()
    return event


# ---------------------------------------------------------------------------
# Analytics summary tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_analytics_summary_empty(client: AsyncClient, auth_headers):
    """Fresh business should return all-zero summary."""
    resp = await client.get("/api/v1/analytics/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_customers"] == 0
    assert data["total_cards"] == 0
    assert data["total_installs"] == 0
    assert data["stamps_issued"] == 0
    assert data["rewards_redeemed"] == 0
    assert data["active_customers"] == 0
    assert data["drifting_customers"] == 0
    assert data["channel_breakdown"] == {}


@pytest.mark.asyncio
async def test_analytics_summary_with_data(
    client: AsyncClient, auth_headers, program, test_session
):
    """Seeded data should be reflected in the summary aggregates."""
    business_id = await _get_business_id(test_session, "owner@example.com")
    result = await test_session.execute(
        select(MerchantUser).where(MerchantUser.email == "owner@example.com")
    )
    user = result.scalar_one()

    now = datetime.utcnow()
    recent = now - timedelta(days=5)
    old = now - timedelta(days=60)

    # Active customer (recent activity)
    cust_active = await _create_customer(
        test_session, business_id, name="Active Customer", enrollment_channel="qr"
    )
    card_active = await _create_card(
        test_session, business_id, cust_active.id, program["id"],
        wallet_platform=WalletPlatform.apple,
        last_activity_at=recent,
        lifetime_stamps=3,
    )
    await _create_scan_event(test_session, card_active.id, business_id, user.id, ScanType.stamp)
    await _create_scan_event(test_session, card_active.id, business_id, user.id, ScanType.stamp)

    # Drifting customer (old activity, enrolled > 14 days ago)
    cust_drift = await _create_customer(
        test_session, business_id, name="Drifting Customer",
        enrolled_at=now - timedelta(days=20),
        enrollment_channel="link",
    )
    card_drift = await _create_card(
        test_session, business_id, cust_drift.id, program["id"],
        wallet_platform=WalletPlatform.none,
        last_activity_at=old,
    )
    await _create_scan_event(test_session, card_drift.id, business_id, user.id, ScanType.stamp)
    await _create_scan_event(test_session, card_drift.id, business_id, user.id, ScanType.redeem)

    await test_session.commit()

    resp = await client.get("/api/v1/analytics/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_customers"] == 2
    assert data["total_cards"] == 2
    assert data["total_installs"] == 1  # only apple counts (not 'none')
    assert data["stamps_issued"] == 3   # 2 for active + 1 for drift
    assert data["rewards_redeemed"] == 1
    assert data["active_customers"] == 1
    assert data["drifting_customers"] == 1
    assert data["channel_breakdown"] == {"qr": 1, "link": 1}


@pytest.mark.asyncio
async def test_analytics_summary_tenant_isolation(client: AsyncClient, test_session):
    """Two businesses must not see each other's stats."""
    # Register business A
    resp_a = await client.post("/api/v1/auth/register", json={
        "email": "biz_a@example.com",
        "password": "passwordA",
        "business_name": "Biz A",
    })
    assert resp_a.status_code == 201
    token_a = resp_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    # Register business B
    resp_b = await client.post("/api/v1/auth/register", json={
        "email": "biz_b@example.com",
        "password": "passwordB",
        "business_name": "Biz B",
    })
    assert resp_b.status_code == 201
    token_b = resp_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Create a program for A
    prog_resp = await client.post("/api/v1/programs", json={
        "name": "A Program",
        "type": "stamp",
        "stamps_required": 5,
        "reward_description": "A Reward",
    }, headers=headers_a)
    assert prog_resp.status_code == 201
    prog_a = prog_resp.json()

    biz_a_id = await _get_business_id(test_session, "biz_a@example.com")
    cust = await _create_customer(test_session, biz_a_id, name="Customer A")
    await _create_card(test_session, biz_a_id, cust.id, prog_a["id"])
    await test_session.commit()

    # Business A sees 1 customer/card
    summary_a = (await client.get("/api/v1/analytics/summary", headers=headers_a)).json()
    assert summary_a["total_customers"] == 1
    assert summary_a["total_cards"] == 1

    # Business B sees 0
    summary_b = (await client.get("/api/v1/analytics/summary", headers=headers_b)).json()
    assert summary_b["total_customers"] == 0
    assert summary_b["total_cards"] == 0


@pytest.mark.asyncio
async def test_analytics_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/analytics/summary")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Customers list tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_customers_empty(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/customers", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_customers_list_basic(client: AsyncClient, auth_headers, program, test_session):
    """Basic list should include customer and joined card fields."""
    business_id = await _get_business_id(test_session, "owner@example.com")

    cust = await _create_customer(
        test_session, business_id, name="Alice", enrollment_channel="qr"
    )
    await _create_card(
        test_session, business_id, cust.id, program["id"],
        current_stamps=3, lifetime_stamps=8, rewards_available=1,
    )
    await test_session.commit()

    resp = await client.get("/api/v1/customers", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    item = data[0]
    assert item["customer_id"] == cust.id
    assert item["name"] == "Alice"
    assert item["enrollment_channel"] == "qr"
    assert item["current_stamps"] == 3
    assert item["lifetime_stamps"] == 8
    assert item["rewards_available"] == 1


@pytest.mark.asyncio
async def test_customers_no_card_appears_with_nulls(
    client: AsyncClient, auth_headers, test_session
):
    """Customers without a card still appear in the list with null card fields."""
    business_id = await _get_business_id(test_session, "owner@example.com")
    await _create_customer(test_session, business_id, name="No-Card Customer")
    await test_session.commit()

    resp = await client.get("/api/v1/customers", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    item = data[0]
    assert item["current_stamps"] is None
    assert item["last_activity_at"] is None
    assert item["status"] is None


@pytest.mark.asyncio
async def test_customers_filter_active(client: AsyncClient, auth_headers, program, test_session):
    """?filter=active returns only customers with recent card activity."""
    business_id = await _get_business_id(test_session, "owner@example.com")
    now = datetime.utcnow()

    cust_recent = await _create_customer(test_session, business_id, name="Recent")
    await _create_card(
        test_session, business_id, cust_recent.id, program["id"],
        last_activity_at=now - timedelta(days=5),
    )

    cust_old = await _create_customer(test_session, business_id, name="Old")
    await _create_card(
        test_session, business_id, cust_old.id, program["id"],
        last_activity_at=now - timedelta(days=45),
    )

    await test_session.commit()

    resp = await client.get("/api/v1/customers?filter=active", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    names = [i["name"] for i in data]
    assert "Recent" in names
    assert "Old" not in names


@pytest.mark.asyncio
async def test_customers_filter_drifting(client: AsyncClient, auth_headers, program, test_session):
    """?filter=drifting returns customers enrolled >14 days ago with no recent activity."""
    business_id = await _get_business_id(test_session, "owner@example.com")
    now = datetime.utcnow()

    # New customer (enrolled 3 days ago) — should NOT be drifting even if no activity
    cust_new = await _create_customer(
        test_session, business_id, name="New Customer",
        enrolled_at=now - timedelta(days=3),
    )

    # Old + active — should NOT be drifting
    cust_old_active = await _create_customer(
        test_session, business_id, name="Old Active",
        enrolled_at=now - timedelta(days=60),
    )
    await _create_card(
        test_session, business_id, cust_old_active.id, program["id"],
        last_activity_at=now - timedelta(days=2),
    )

    # Old + no card — should be drifting
    cust_old_nocard = await _create_customer(
        test_session, business_id, name="Old No-Card",
        enrolled_at=now - timedelta(days=30),
    )

    # Old + old activity — should be drifting
    cust_old_inactive = await _create_customer(
        test_session, business_id, name="Old Inactive",
        enrolled_at=now - timedelta(days=60),
    )
    await _create_card(
        test_session, business_id, cust_old_inactive.id, program["id"],
        last_activity_at=now - timedelta(days=50),
    )

    await test_session.commit()

    resp = await client.get("/api/v1/customers?filter=drifting", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    names = [i["name"] for i in data]
    assert "Old No-Card" in names
    assert "Old Inactive" in names
    assert "New Customer" not in names
    assert "Old Active" not in names


@pytest.mark.asyncio
async def test_customers_filter_top(client: AsyncClient, auth_headers, program, test_session):
    """?filter=top returns customers ordered by lifetime_stamps descending."""
    business_id = await _get_business_id(test_session, "owner@example.com")

    cust_a = await _create_customer(test_session, business_id, name="A-5stamps")
    await _create_card(
        test_session, business_id, cust_a.id, program["id"], lifetime_stamps=5
    )

    cust_b = await _create_customer(test_session, business_id, name="B-20stamps")
    await _create_card(
        test_session, business_id, cust_b.id, program["id"], lifetime_stamps=20
    )

    cust_c = await _create_customer(test_session, business_id, name="C-1stamp")
    await _create_card(
        test_session, business_id, cust_c.id, program["id"], lifetime_stamps=1
    )

    await test_session.commit()

    resp = await client.get("/api/v1/customers?filter=top", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    stamps = [i["lifetime_stamps"] for i in data]
    # Must be descending
    assert stamps == sorted(stamps, reverse=True)
    assert stamps[0] == 20


@pytest.mark.asyncio
async def test_customers_pagination(client: AsyncClient, auth_headers, test_session):
    """limit and offset must correctly paginate results."""
    business_id = await _get_business_id(test_session, "owner@example.com")

    for i in range(5):
        await _create_customer(test_session, business_id, name=f"Cust {i}")
    await test_session.commit()

    resp_all = await client.get("/api/v1/customers?limit=5&offset=0", headers=auth_headers)
    assert len(resp_all.json()) == 5

    resp_first = await client.get("/api/v1/customers?limit=2&offset=0", headers=auth_headers)
    assert len(resp_first.json()) == 2

    resp_second = await client.get("/api/v1/customers?limit=2&offset=2", headers=auth_headers)
    assert len(resp_second.json()) == 2

    resp_tail = await client.get("/api/v1/customers?limit=2&offset=4", headers=auth_headers)
    assert len(resp_tail.json()) == 1

    # Verify non-overlapping pages
    ids_first = {i["customer_id"] for i in resp_first.json()}
    ids_second = {i["customer_id"] for i in resp_second.json()}
    assert ids_first.isdisjoint(ids_second)


@pytest.mark.asyncio
async def test_customers_tenant_isolation(client: AsyncClient, test_session):
    """Each business must only see its own customers."""
    resp_a = await client.post("/api/v1/auth/register", json={
        "email": "iso_a@example.com",
        "password": "passA",
        "business_name": "Iso Biz A",
    })
    token_a = resp_a.json()["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    resp_b = await client.post("/api/v1/auth/register", json={
        "email": "iso_b@example.com",
        "password": "passB",
        "business_name": "Iso Biz B",
    })
    token_b = resp_b.json()["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    biz_a_id = await _get_business_id(test_session, "iso_a@example.com")
    biz_b_id = await _get_business_id(test_session, "iso_b@example.com")

    await _create_customer(test_session, biz_a_id, name="A Customer")
    await _create_customer(test_session, biz_b_id, name="B Customer")
    await test_session.commit()

    custs_a = (await client.get("/api/v1/customers", headers=headers_a)).json()
    custs_b = (await client.get("/api/v1/customers", headers=headers_b)).json()

    assert len(custs_a) == 1
    assert custs_a[0]["name"] == "A Customer"

    assert len(custs_b) == 1
    assert custs_b[0]["name"] == "B Customer"


@pytest.mark.asyncio
async def test_customers_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/customers")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_customers_invalid_filter(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/customers?filter=invalid", headers=auth_headers)
    assert resp.status_code == 422
