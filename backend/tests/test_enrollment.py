"""Tests for Phase 2 — enrollment flow, stub wallet pass page, enrollment QR."""

import secrets
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlmodel import select

from app.models.customer import Customer, ContactType
from app.models.loyalty_card import LoyaltyCard, WalletPlatform, CardStatus
from app.models.scan_event import ScanEvent
from app.models.user import MerchantUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_and_program(client: AsyncClient, *, email: str, biz_name: str, stamps: int = 9):
    """Register a user + create an active reward program. Returns (headers, program_dict, slug)."""
    reg = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "testpass123",
        "business_name": biz_name,
    })
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    prog = await client.post("/api/v1/programs", json={
        "name": "Test Programme",
        "type": "stamp",
        "stamps_required": stamps,
        "reward_description": f"Buy {stamps}, get the {stamps + 1}th free",
    }, headers=headers)
    assert prog.status_code == 201

    biz = await client.get("/api/v1/business", headers=headers)
    assert biz.status_code == 200
    slug = biz.json()["slug"]

    return headers, prog.json(), slug


# ---------------------------------------------------------------------------
# GET /e/{business_slug}  — Enrollment landing page
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrollment_landing_renders(client: AsyncClient):
    """Landing page returns 200 and contains the business name."""
    headers, program, slug = await _register_and_program(
        client, email="landing@example.com", biz_name="Landing Café"
    )
    resp = await client.get(f"/e/{slug}")
    assert resp.status_code == 200
    assert "Landing Café" in resp.text
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_enrollment_landing_contains_reward_description(client: AsyncClient):
    """Landing page contains the program reward description."""
    headers, program, slug = await _register_and_program(
        client, email="landing2@example.com", biz_name="Stamp Shop", stamps=5
    )
    resp = await client.get(f"/e/{slug}")
    assert resp.status_code == 200
    assert "Buy 5, get the 6th free" in resp.text


@pytest.mark.asyncio
async def test_enrollment_landing_404_for_unknown_slug(client: AsyncClient):
    """Landing page returns 404 for an unknown slug."""
    resp = await client.get("/e/totally-unknown-slug-xyz123")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_enrollment_landing_no_active_program(client: AsyncClient):
    """Landing page shows 'not accepting enrollments' when no active program exists."""
    reg = await client.post("/api/v1/auth/register", json={
        "email": "noprog@example.com",
        "password": "testpass123",
        "business_name": "No Programme Biz",
    })
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    biz = await client.get("/api/v1/business", headers=headers)
    slug = biz.json()["slug"]

    # No program created — landing page should show friendly message
    resp = await client.get(f"/e/{slug}")
    assert resp.status_code == 200
    assert "not accepting" in resp.text.lower() or "no programme" in resp.text.lower() or "not accepting new" in resp.text.lower()


# ---------------------------------------------------------------------------
# POST /api/v1/e/{business_slug}/enroll  — JSON enrollment endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enroll_creates_customer_and_card(client: AsyncClient):
    """Enrollment creates a customer + card and returns expected fields."""
    headers, program, slug = await _register_and_program(
        client, email="enrolltest@example.com", biz_name="Enroll Biz", stamps=9
    )
    resp = await client.post(f"/api/v1/e/{slug}/enroll", json={
        "name": "Alice",
        "contact": "alice@example.com",
        "contact_type": "email",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "customer_id" in data
    assert "card_id" in data
    assert "pass_serial" in data
    assert "pass_url" in data
    assert data["current_stamps"] == 0
    assert data["stamps_required"] == 9
    assert "9" in data["reward_description"]  # "Buy 9, get the 10th free"


@pytest.mark.asyncio
async def test_enroll_pass_url_points_to_pass_page(client: AsyncClient):
    """The pass_url returned by enroll should be a /pass/<serial> URL."""
    headers, program, slug = await _register_and_program(
        client, email="passurl@example.com", biz_name="Pass URL Biz"
    )
    resp = await client.post(f"/api/v1/e/{slug}/enroll", json={
        "name": "Bob",
        "contact": "bob@example.com",
        "contact_type": "email",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["pass_url"].endswith(f"/pass/{data['pass_serial']}")


@pytest.mark.asyncio
async def test_enroll_no_active_program_returns_400(client: AsyncClient):
    """Enrolling into a business with no active program returns 400."""
    reg = await client.post("/api/v1/auth/register", json={
        "email": "noprog2@example.com",
        "password": "testpass123",
        "business_name": "No Active Prog",
    })
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    biz = await client.get("/api/v1/business", headers=headers)
    slug = biz.json()["slug"]

    resp = await client.post(f"/api/v1/e/{slug}/enroll", json={
        "name": "Charlie",
        "contact": "charlie@example.com",
        "contact_type": "email",
    })
    assert resp.status_code == 400
    assert "active" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_enroll_unknown_slug_returns_404(client: AsyncClient):
    """Enrolling into an unknown business slug returns 404."""
    resp = await client.post("/api/v1/e/no-such-biz-xyz/enroll", json={
        "name": "Dave",
        "contact": "dave@example.com",
        "contact_type": "email",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_enroll_phone_contact_type(client: AsyncClient):
    """Enrollment works with phone contact_type."""
    headers, program, slug = await _register_and_program(
        client, email="phoneenroll@example.com", biz_name="Phone Biz"
    )
    resp = await client.post(f"/api/v1/e/{slug}/enroll", json={
        "name": "Eve",
        "contact": "+15550001234",
        "contact_type": "phone",
    })
    assert resp.status_code == 200
    assert resp.json()["current_stamps"] == 0


# ---------------------------------------------------------------------------
# GET /pass/{pass_serial}  — Stub wallet pass page
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pass_page_renders_for_valid_card(client: AsyncClient):
    """Pass page returns 200 HTML for a valid card, with stamp count visible."""
    headers, program, slug = await _register_and_program(
        client, email="passpage@example.com", biz_name="Pass Page Biz", stamps=5
    )
    enroll = await client.post(f"/api/v1/e/{slug}/enroll", json={
        "name": "Frank",
        "contact": "frank@example.com",
        "contact_type": "email",
    })
    assert enroll.status_code == 200
    data = enroll.json()
    pass_url = data["pass_url"]  # e.g. http://localhost:8000/pass/<serial>
    pass_serial = data["pass_serial"]

    # The test client uses http://test as base; derive relative path
    resp = await client.get(f"/pass/{pass_serial}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    # Should show "0" stamps (initial state) and the total
    assert "0" in resp.text
    assert "5" in resp.text


@pytest.mark.asyncio
async def test_pass_page_404_for_unknown_serial(client: AsyncClient):
    """Pass page returns 404 for an unknown pass serial."""
    resp = await client.get("/pass/totally-fake-serial-that-does-not-exist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_pass_page_contains_business_name(client: AsyncClient):
    """Pass page contains the business name."""
    headers, program, slug = await _register_and_program(
        client, email="passname@example.com", biz_name="Named Biz"
    )
    enroll = await client.post(f"/api/v1/e/{slug}/enroll", json={
        "name": "Grace",
        "contact": "grace@example.com",
        "contact_type": "email",
    })
    assert enroll.status_code == 200
    serial = enroll.json()["pass_serial"]

    resp = await client.get(f"/pass/{serial}")
    assert resp.status_code == 200
    assert "Named Biz" in resp.text


@pytest.mark.asyncio
async def test_pass_page_reflects_updated_stamp_count(client: AsyncClient, test_session):
    """After enrolling and stamping, the pass page shows the updated stamp count."""
    headers, program, slug = await _register_and_program(
        client, email="stampupdate@example.com", biz_name="Stamp Update Biz", stamps=9
    )
    enroll = await client.post(f"/api/v1/e/{slug}/enroll", json={
        "name": "Hank",
        "contact": "hank@example.com",
        "contact_type": "email",
    })
    assert enroll.status_code == 200
    data = enroll.json()
    serial = data["pass_serial"]
    card_id = data["card_id"]

    # Find the card's barcode_token via the DB
    result = await test_session.execute(
        select(LoyaltyCard).where(LoyaltyCard.id == card_id)
    )
    card = result.scalar_one()
    barcode_token = card.barcode_token

    # Stamp once via the scan endpoint
    stamp_resp = await client.post("/api/v1/scan", json={
        "barcode_token": barcode_token,
        "action": "stamp",
    }, headers=headers)
    assert stamp_resp.status_code == 200
    assert stamp_resp.json()["current_stamps"] == 1

    # Pass page should now show "1" stamps
    pass_resp = await client.get(f"/pass/{serial}")
    assert pass_resp.status_code == 200
    assert "1" in pass_resp.text


@pytest.mark.asyncio
async def test_pass_page_shows_rewards_available_banner(client: AsyncClient, test_session):
    """Pass page shows a 'reward available' banner when rewards_available > 0."""
    headers, program, slug = await _register_and_program(
        client, email="rewardbanner@example.com", biz_name="Reward Banner Biz", stamps=1
    )
    enroll = await client.post(f"/api/v1/e/{slug}/enroll", json={
        "name": "Iris",
        "contact": "iris@example.com",
        "contact_type": "email",
    })
    assert enroll.status_code == 200
    data = enroll.json()
    serial = data["pass_serial"]
    card_id = data["card_id"]

    result = await test_session.execute(
        select(LoyaltyCard).where(LoyaltyCard.id == card_id)
    )
    card = result.scalar_one()

    # Stamp once — with stamps_required=1, this earns a reward
    await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=headers)

    pass_resp = await client.get(f"/pass/{serial}")
    assert pass_resp.status_code == 200
    assert "reward" in pass_resp.text.lower()


# ---------------------------------------------------------------------------
# GET /api/v1/enrollment-qr  — Enrollment QR endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrollment_qr_returns_png_when_authed(client: AsyncClient):
    """enrollment-qr returns a PNG when authenticated."""
    headers, program, slug = await _register_and_program(
        client, email="qrtest@example.com", biz_name="QR Test Biz"
    )
    resp = await client.get("/api/v1/enrollment-qr", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    # PNG magic bytes: \x89PNG
    assert resp.content[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_enrollment_qr_returns_401_without_auth(client: AsyncClient):
    """enrollment-qr returns 401 when not authenticated."""
    resp = await client.get("/api/v1/enrollment-qr")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_enrollment_qr_pdf_format(client: AsyncClient):
    """enrollment-qr?format=pdf returns a PDF when authenticated."""
    headers, program, slug = await _register_and_program(
        client, email="qrpdf@example.com", biz_name="QR PDF Biz"
    )
    resp = await client.get("/api/v1/enrollment-qr?format=pdf", headers=headers)
    assert resp.status_code == 200
    assert "pdf" in resp.headers["content-type"]
    # PDF magic bytes: %PDF
    assert resp.content[:4] == b"%PDF"
