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


async def create_card_for_user(
    client: AsyncClient,
    auth_headers: dict,
    test_session,
    program_id: int,
    stamps_required: int = 5,
) -> LoyaltyCard:
    """Helper to create a loyalty card for a given program."""
    result = await test_session.execute(
        select(MerchantUser).where(MerchantUser.email == "owner@example.com")
    )
    user = result.scalar_one()
    business_id = user.business_id

    customer = Customer(
        business_id=business_id,
        name="Scan Test Customer",
        email=f"scantest-{secrets.token_hex(4)}@example.com",
        email_verified=True,
        enrolled_at=datetime.utcnow(),
        enrollment_channel="web",
    )
    test_session.add(customer)
    await test_session.flush()

    card = LoyaltyCard(
        business_id=business_id,
        customer_id=customer.id,
        program_id=program_id,
        barcode_token=secrets.token_urlsafe(32),
        pass_serial=str(uuid.uuid4()),
        wallet_platform=WalletPlatform.stub,
        status=CardStatus.active,
    )
    test_session.add(card)
    await test_session.commit()
    await test_session.refresh(card)
    return card


@pytest.mark.asyncio
async def test_stamp_success(client: AsyncClient, auth_headers, program, test_session):
    card = await create_card_for_user(client, auth_headers, test_session, program["id"])

    response = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "stamp"
    assert data["current_stamps"] == 1
    assert data["lifetime_stamps"] == 1
    assert data["rewards_available"] == 0


@pytest.mark.asyncio
async def test_full_stamp_loop_earns_reward(client: AsyncClient, auth_headers, test_session):
    """Stamping up to stamps_required should earn a reward and reset stamps."""
    # Create a program with 3 stamps required
    prog_resp = await client.post("/api/v1/programs", json={
        "name": "Quick Stamp Program",
        "type": "stamp",
        "stamps_required": 3,
        "reward_description": "Quick reward",
    }, headers=auth_headers)
    prog = prog_resp.json()

    card = await create_card_for_user(client, auth_headers, test_session, prog["id"])

    # Stamp 1 - need to patch time to bypass throttle or set throttle to 0
    # We'll directly manipulate scan events to simulate past stamps
    # First stamp
    r1 = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=auth_headers)
    assert r1.status_code == 200
    assert r1.json()["current_stamps"] == 1
    assert r1.json()["rewards_available"] == 0

    # Manually move the scan event back in time to bypass throttle
    result = await test_session.execute(
        select(ScanEvent).where(ScanEvent.card_id == card.id)
    )
    events = result.scalars().all()
    for event in events:
        event.created_at = datetime.utcnow() - timedelta(minutes=10)
        test_session.add(event)
    await test_session.commit()

    # Stamp 2
    r2 = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["current_stamps"] == 2

    # Move events back again
    result = await test_session.execute(
        select(ScanEvent).where(ScanEvent.card_id == card.id)
    )
    events = result.scalars().all()
    for event in events:
        event.created_at = datetime.utcnow() - timedelta(minutes=10)
        test_session.add(event)
    await test_session.commit()

    # Stamp 3 - should earn reward and reset stamps
    r3 = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=auth_headers)
    assert r3.status_code == 200
    data = r3.json()
    assert data["current_stamps"] == 0  # reset after earning reward
    assert data["rewards_available"] == 1
    assert data["lifetime_stamps"] == 3


@pytest.mark.asyncio
async def test_redeem_success(client: AsyncClient, auth_headers, test_session):
    """Redeeming a reward should decrement rewards_available."""
    prog_resp = await client.post("/api/v1/programs", json={
        "name": "Redeem Test Program",
        "type": "stamp",
        "stamps_required": 1,  # Easy to earn
        "reward_description": "Instant reward",
    }, headers=auth_headers)
    prog = prog_resp.json()

    card = await create_card_for_user(client, auth_headers, test_session, prog["id"])

    # Stamp to earn a reward (1 stamp = 1 reward with stamps_required=1)
    r = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["rewards_available"] == 1

    # Redeem
    r2 = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "redeem",
    }, headers=auth_headers)
    assert r2.status_code == 200
    data = r2.json()
    assert data["action"] == "redeem"
    assert data["rewards_available"] == 0


@pytest.mark.asyncio
async def test_redeem_no_rewards_returns_400(client: AsyncClient, auth_headers, loyalty_card):
    """Redeeming without any rewards should return 400."""
    response = await client.post("/api/v1/scan", json={
        "barcode_token": loyalty_card.barcode_token,
        "action": "redeem",
    }, headers=auth_headers)
    assert response.status_code == 400
    assert "no rewards" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_stamp_throttle_rejection(client: AsyncClient, auth_headers, loyalty_card):
    """Stamping the same card twice within the throttle window should return 429."""
    # First stamp - should succeed
    r1 = await client.post("/api/v1/scan", json={
        "barcode_token": loyalty_card.barcode_token,
        "action": "stamp",
    }, headers=auth_headers)
    assert r1.status_code == 200

    # Second stamp immediately - should be throttled
    r2 = await client.post("/api/v1/scan", json={
        "barcode_token": loyalty_card.barcode_token,
        "action": "stamp",
    }, headers=auth_headers)
    assert r2.status_code == 429


@pytest.mark.asyncio
async def test_stamp_after_throttle_window(client: AsyncClient, auth_headers, test_session, program):
    """Stamping after the throttle window has passed should succeed."""
    card = await create_card_for_user(client, auth_headers, test_session, program["id"])

    # First stamp
    r1 = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=auth_headers)
    assert r1.status_code == 200

    # Simulate time passing by moving the event's created_at back
    result = await test_session.execute(
        select(ScanEvent).where(ScanEvent.card_id == card.id)
    )
    events = result.scalars().all()
    for event in events:
        event.created_at = datetime.utcnow() - timedelta(minutes=10)
        test_session.add(event)
    await test_session.commit()

    # Second stamp after window - should succeed
    r2 = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=auth_headers)
    assert r2.status_code == 200
    assert r2.json()["current_stamps"] == 2


@pytest.mark.asyncio
async def test_cross_tenant_scan_rejection(client: AsyncClient, test_session):
    """A staff member should not be able to scan cards from another business."""
    # Register two tenants
    resp1 = await client.post("/api/v1/auth/register", json={
        "email": "scan_tenant1@example.com",
        "password": "password1",
        "business_name": "Scan Tenant 1",
    })
    token1 = resp1.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    resp2 = await client.post("/api/v1/auth/register", json={
        "email": "scan_tenant2@example.com",
        "password": "password2",
        "business_name": "Scan Tenant 2",
    })
    token2 = resp2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # Tenant 1 creates a program
    prog_resp = await client.post("/api/v1/programs", json={
        "name": "Tenant 1 Program",
        "type": "stamp",
        "stamps_required": 5,
        "reward_description": "Tenant 1 Reward",
    }, headers=headers1)
    prog1 = prog_resp.json()

    # Get tenant 1 user to create a card
    result = await test_session.execute(
        select(MerchantUser).where(MerchantUser.email == "scan_tenant1@example.com")
    )
    user1 = result.scalar_one()

    customer1 = Customer(
        business_id=user1.business_id,
        name="Tenant 1 Customer",
        email="t1cust@example.com",
        email_verified=True,
        enrolled_at=datetime.utcnow(),
        enrollment_channel="web",
    )
    test_session.add(customer1)
    await test_session.flush()

    card1 = LoyaltyCard(
        business_id=user1.business_id,
        customer_id=customer1.id,
        program_id=prog1["id"],
        barcode_token=secrets.token_urlsafe(32),
        pass_serial=str(uuid.uuid4()),
        wallet_platform=WalletPlatform.stub,
        status=CardStatus.active,
    )
    test_session.add(card1)
    await test_session.commit()
    await test_session.refresh(card1)

    # Tenant 2 tries to scan tenant 1's card - should be rejected with 403
    response = await client.post("/api/v1/scan", json={
        "barcode_token": card1.barcode_token,
        "action": "stamp",
    }, headers=headers2)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_scan_invalid_barcode(client: AsyncClient, auth_headers):
    """Scanning with an unknown barcode token should return 404."""
    response = await client.post("/api/v1/scan", json={
        "barcode_token": "completely-invalid-token-that-does-not-exist",
        "action": "stamp",
    }, headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_scan_idempotency(client: AsyncClient, auth_headers, loyalty_card):
    """Scanning with the same idempotency key twice should not double-process."""
    idempotency_key = "test-idempotency-key-12345"

    # First scan
    r1 = await client.post("/api/v1/scan", json={
        "barcode_token": loyalty_card.barcode_token,
        "action": "stamp",
    }, headers={**auth_headers, "X-Idempotency-Key": idempotency_key})
    assert r1.status_code == 200
    stamps_after_first = r1.json()["current_stamps"]

    # Second scan with same idempotency key - should not process again
    r2 = await client.post("/api/v1/scan", json={
        "barcode_token": loyalty_card.barcode_token,
        "action": "stamp",
    }, headers={**auth_headers, "X-Idempotency-Key": idempotency_key})
    assert r2.status_code == 200
    # Stamps should not have increased
    assert r2.json()["current_stamps"] == stamps_after_first


@pytest.mark.asyncio
async def test_complete_register_login_stamp_redeem_cycle(client: AsyncClient, test_session):
    """Full end-to-end test: register, login, create program, stamp, redeem."""
    # 1. Register
    reg_resp = await client.post("/api/v1/auth/register", json={
        "email": "cycle@example.com",
        "password": "cyclepass123",
        "business_name": "Cycle Business",
    })
    assert reg_resp.status_code == 201
    access_token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 2. Login to get fresh tokens
    login_resp = await client.post("/api/v1/auth/login", json={
        "email": "cycle@example.com",
        "password": "cyclepass123",
    })
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    # 3. Create program with 2 stamps required
    prog_resp = await client.post("/api/v1/programs", json={
        "name": "Cycle Program",
        "type": "stamp",
        "stamps_required": 2,
        "reward_description": "Cycle reward",
    }, headers=headers)
    assert prog_resp.status_code == 201
    prog = prog_resp.json()

    # 4. Create card
    result = await test_session.execute(
        select(MerchantUser).where(MerchantUser.email == "cycle@example.com")
    )
    user = result.scalar_one()

    customer = Customer(
        business_id=user.business_id,
        name="Cycle Customer",
        email="cyclecust@example.com",
        email_verified=True,
        enrolled_at=datetime.utcnow(),
        enrollment_channel="web",
    )
    test_session.add(customer)
    await test_session.flush()

    card = LoyaltyCard(
        business_id=user.business_id,
        customer_id=customer.id,
        program_id=prog["id"],
        barcode_token=secrets.token_urlsafe(32),
        pass_serial=str(uuid.uuid4()),
        wallet_platform=WalletPlatform.stub,
        status=CardStatus.active,
    )
    test_session.add(card)
    await test_session.commit()
    await test_session.refresh(card)

    # 5. Stamp 1
    r1 = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=headers)
    assert r1.status_code == 200
    assert r1.json()["current_stamps"] == 1
    assert r1.json()["rewards_available"] == 0

    # Move event back in time to bypass throttle
    result = await test_session.execute(
        select(ScanEvent).where(ScanEvent.card_id == card.id)
    )
    events = result.scalars().all()
    for event in events:
        event.created_at = datetime.utcnow() - timedelta(minutes=10)
        test_session.add(event)
    await test_session.commit()

    # 6. Stamp 2 - earns reward
    r2 = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["current_stamps"] == 0  # reset
    assert r2.json()["rewards_available"] == 1
    assert r2.json()["lifetime_stamps"] == 2

    # 7. Redeem
    r3 = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "redeem",
    }, headers=headers)
    assert r3.status_code == 200
    assert r3.json()["rewards_available"] == 0

    # 8. Try to redeem again - should fail with 400
    r4 = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "redeem",
    }, headers=headers)
    assert r4.status_code == 400

    # 9. Refresh token
    refresh_resp = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": login_resp.json()["refresh_token"],
    })
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()
