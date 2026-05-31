"""Legacy enrollment tests — replaced by test_enrollment_v2.py.

The POST /enroll endpoint has been removed; tests that used it have been
migrated to test_enrollment_v2.py which covers the new OTP + Google flow.

Only the pass-page and enrollment-QR tests that don't depend on the old
/enroll endpoint are kept here.
"""

import pytest
from httpx import AsyncClient
from sqlmodel import select

from app.models.loyalty_card import LoyaltyCard


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


async def _do_otp_enroll(client, slug, name="Test User", email="test@example.com"):
    """Enroll via OTP and return the EnrollResponse dict."""
    from unittest.mock import AsyncMock, MagicMock, patch

    captured = []

    async def fake_send_otp(to_email, code, business_name):
        captured.append(code)

    mock_provider = MagicMock()
    mock_provider.send_otp = fake_send_otp

    with patch("app.api.v1.enrollment.get_email_provider", return_value=mock_provider):
        req = await client.post(f"/api/v1/e/{slug}/otp/request", json={
            "name": name, "email": email,
        })
    assert req.status_code == 200

    verify = await client.post(f"/api/v1/e/{slug}/otp/verify", json={
        "name": name, "email": email, "code": captured[0],
    })
    assert verify.status_code == 200
    return verify.json()


# ---------------------------------------------------------------------------
# GET /pass/{pass_serial}  — Stub wallet pass page
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pass_page_renders_for_valid_card(client: AsyncClient):
    """Pass page returns 200 HTML for a valid card, with stamp count visible."""
    headers, program, slug = await _register_and_program(
        client, email="passpage@example.com", biz_name="Pass Page Biz", stamps=5
    )
    data = await _do_otp_enroll(client, slug, email="frank@example.com")
    pass_serial = data["pass_serial"]

    resp = await client.get(f"/pass/{pass_serial}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
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
    data = await _do_otp_enroll(client, slug, email="grace@example.com")
    resp = await client.get(f"/pass/{data['pass_serial']}")
    assert resp.status_code == 200
    assert "Named Biz" in resp.text


@pytest.mark.asyncio
async def test_pass_page_reflects_updated_stamp_count(client: AsyncClient, test_session):
    """After enrolling and stamping, the pass page shows the updated stamp count."""
    headers, program, slug = await _register_and_program(
        client, email="stampupdate@example.com", biz_name="Stamp Update Biz", stamps=9
    )
    data = await _do_otp_enroll(client, slug, email="hank@example.com")
    serial = data["pass_serial"]
    card_id = data["card_id"]

    result = await test_session.execute(
        select(LoyaltyCard).where(LoyaltyCard.id == card_id)
    )
    card = result.scalar_one()

    stamp_resp = await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=headers)
    assert stamp_resp.status_code == 200
    assert stamp_resp.json()["current_stamps"] == 1

    pass_resp = await client.get(f"/pass/{serial}")
    assert pass_resp.status_code == 200
    assert "1" in pass_resp.text


@pytest.mark.asyncio
async def test_pass_page_shows_rewards_available_banner(client: AsyncClient, test_session):
    """Pass page shows a 'reward available' banner when rewards_available > 0."""
    headers, program, slug = await _register_and_program(
        client, email="rewardbanner@example.com", biz_name="Reward Banner Biz", stamps=1
    )
    data = await _do_otp_enroll(client, slug, email="iris@example.com")
    serial = data["pass_serial"]
    card_id = data["card_id"]

    result = await test_session.execute(
        select(LoyaltyCard).where(LoyaltyCard.id == card_id)
    )
    card = result.scalar_one()

    await client.post("/api/v1/scan", json={
        "barcode_token": card.barcode_token,
        "action": "stamp",
    }, headers=headers)

    pass_resp = await client.get(f"/pass/{serial}")
    assert pass_resp.status_code == 200
    assert "reward" in pass_resp.text.lower()


# ---------------------------------------------------------------------------
# GET /api/v1/enrollment-qr
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrollment_qr_returns_png_when_authed(client: AsyncClient):
    """enrollment-qr returns a PNG when authenticated."""
    headers, program, slug = await _register_and_program(
        client, email="qrtest2@example.com", biz_name="QR Test Biz 2"
    )
    resp = await client.get("/api/v1/enrollment-qr", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
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
    assert resp.content[:4] == b"%PDF"
