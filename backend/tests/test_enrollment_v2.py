"""Tests for Phase — verified enrollment flow (OTP + Google OAuth)."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.customer import Customer
from app.models.enrollment_otp import EnrollmentOTP
from app.models.loyalty_card import LoyaltyCard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _register_and_program(client: AsyncClient, *, email: str, biz_name: str, stamps: int = 5):
    """Register a merchant user + create an active reward program. Returns (headers, slug)."""
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
        "reward_description": f"Buy {stamps} get 1 free",
    }, headers=headers)
    assert prog.status_code == 201

    biz = await client.get("/api/v1/business", headers=headers)
    assert biz.status_code == 200
    slug = biz.json()["slug"]

    return headers, slug


# ---------------------------------------------------------------------------
# OTP request
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_otp_request_returns_sent_true(client: AsyncClient):
    """OTP request always returns {sent: true}."""
    _headers, slug = await _register_and_program(
        client, email="otpreq@example.com", biz_name="OTP Req Biz"
    )
    with patch(
        "app.api.v1.enrollment.get_email_provider",
        return_value=AsyncMock(send_otp=AsyncMock()),
    ):
        resp = await client.post(f"/api/v1/e/{slug}/otp/request", json={
            "name": "Alice",
            "email": "alice@example.com",
        })
    assert resp.status_code == 200
    assert resp.json() == {"sent": True}


@pytest.mark.asyncio
async def test_otp_request_creates_otp_row_with_hashed_code(client: AsyncClient, test_session):
    """OTP request creates an EnrollmentOTP row; code is hashed, not stored in plain."""
    _headers, slug = await _register_and_program(
        client, email="otprow@example.com", biz_name="OTP Row Biz"
    )
    captured_codes = []

    async def fake_send_otp(to_email, code, business_name):
        captured_codes.append(code)

    mock_provider = MagicMock()
    mock_provider.send_otp = fake_send_otp

    with patch("app.api.v1.enrollment.get_email_provider", return_value=mock_provider):
        resp = await client.post(f"/api/v1/e/{slug}/otp/request", json={
            "name": "Alice",
            "email": "alice-row@example.com",
        })
    assert resp.status_code == 200

    # There should be an OTP row in the DB
    result = await test_session.execute(
        select(EnrollmentOTP).where(EnrollmentOTP.email == "alice-row@example.com")
    )
    otp = result.scalar_one_or_none()
    assert otp is not None
    # code_hash must differ from the plain code
    assert len(captured_codes) == 1
    plain_code = captured_codes[0]
    assert otp.code_hash != plain_code
    # code_hash should be a bcrypt hash
    assert otp.code_hash.startswith("$2b$") or otp.code_hash.startswith("$2a$")


@pytest.mark.asyncio
async def test_otp_request_replaces_existing_otp(client: AsyncClient, test_session):
    """Re-requesting OTP for same email replaces the old row (new code_hash, exactly one row)."""
    _headers, slug = await _register_and_program(
        client, email="otpreplace@example.com", biz_name="OTP Replace Biz"
    )
    captured_codes = []

    async def fake_send_otp(to_email, code, business_name):
        captured_codes.append(code)

    mock_provider = MagicMock()
    mock_provider.send_otp = fake_send_otp

    with patch("app.api.v1.enrollment.get_email_provider", return_value=mock_provider):
        await client.post(f"/api/v1/e/{slug}/otp/request", json={
            "name": "Alice",
            "email": "alice-replace@example.com",
        })
        first_result = await test_session.execute(
            select(EnrollmentOTP).where(EnrollmentOTP.email == "alice-replace@example.com")
        )
        first_otp = first_result.scalar_one()
        first_hash = first_otp.code_hash

        await client.post(f"/api/v1/e/{slug}/otp/request", json={
            "name": "Alice",
            "email": "alice-replace@example.com",
        })

    # Exactly one row for this email; hash changed (new code was generated)
    test_session.expire_all()
    second_result = await test_session.execute(
        select(EnrollmentOTP).where(EnrollmentOTP.email == "alice-replace@example.com")
    )
    rows = second_result.scalars().all()
    assert len(rows) == 1
    # The second code was different from the first (with overwhelming probability)
    assert len(captured_codes) == 2
    # The stored hash should match the second code, not the first
    from app.core.security import verify_password
    assert verify_password(captured_codes[1], rows[0].code_hash)


@pytest.mark.asyncio
async def test_otp_request_returns_200_even_when_email_send_fails(client: AsyncClient):
    """OTP request returns 200 even if the email provider raises an exception."""
    _headers, slug = await _register_and_program(
        client, email="otpfail@example.com", biz_name="OTP Fail Biz"
    )
    mock_provider = MagicMock()
    mock_provider.send_otp = AsyncMock(side_effect=Exception("SMTP error"))

    with patch("app.api.v1.enrollment.get_email_provider", return_value=mock_provider):
        resp = await client.post(f"/api/v1/e/{slug}/otp/request", json={
            "name": "Alice",
            "email": "alice-fail@example.com",
        })
    assert resp.status_code == 200
    assert resp.json()["sent"] is True


@pytest.mark.asyncio
async def test_otp_request_404_for_unknown_slug(client: AsyncClient):
    resp = await client.post("/api/v1/e/no-such-biz-xyz/otp/request", json={
        "name": "Alice",
        "email": "alice@example.com",
    })
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# OTP verify — happy path
# ---------------------------------------------------------------------------

async def _do_otp_flow(client, slug, name="Alice", email="alice@example.com"):
    """Helper: request OTP (capture code) then verify. Returns verify response."""
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
    assert captured, "Email provider was not called — code not captured"

    verify = await client.post(f"/api/v1/e/{slug}/otp/verify", json={
        "name": name, "email": email, "code": captured[0],
    })
    return verify


@pytest.mark.asyncio
async def test_otp_verify_correct_code_returns_enroll_response(client: AsyncClient):
    _headers, slug = await _register_and_program(
        client, email="verifyhappy@example.com", biz_name="Verify Happy Biz"
    )
    resp = await _do_otp_flow(client, slug)
    assert resp.status_code == 200
    data = resp.json()
    assert "customer_id" in data
    assert "card_id" in data
    assert "pass_serial" in data
    assert "pass_url" in data
    assert "email" in data
    assert data["email"] == "alice@example.com"
    assert data["email_verified"] is True
    assert data["pass_url"].endswith(f"/pass/{data['pass_serial']}")


@pytest.mark.asyncio
async def test_otp_verify_deletes_otp_row(client: AsyncClient, test_session):
    """After successful verify, the OTP row must be deleted (one-time use)."""
    _headers, slug = await _register_and_program(
        client, email="verifydel@example.com", biz_name="Verify Delete Biz"
    )
    await _do_otp_flow(client, slug, email="alice-del@example.com")

    result = await test_session.execute(
        select(EnrollmentOTP).where(EnrollmentOTP.email == "alice-del@example.com")
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# OTP verify — wrong code / lockout / expiry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_otp_verify_wrong_code_returns_400(client: AsyncClient):
    _headers, slug = await _register_and_program(
        client, email="wrongcode@example.com", biz_name="Wrong Code Biz"
    )
    mock_provider = MagicMock()
    mock_provider.send_otp = AsyncMock()

    with patch("app.api.v1.enrollment.get_email_provider", return_value=mock_provider):
        await client.post(f"/api/v1/e/{slug}/otp/request", json={
            "name": "Alice", "email": "alice-wrong@example.com",
        })

    resp = await client.post(f"/api/v1/e/{slug}/otp/verify", json={
        "name": "Alice", "email": "alice-wrong@example.com", "code": "000000",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_otp_verify_increments_attempts_on_wrong_code(client: AsyncClient, test_session):
    _headers, slug = await _register_and_program(
        client, email="attempts@example.com", biz_name="Attempts Biz"
    )
    mock_provider = MagicMock()
    mock_provider.send_otp = AsyncMock()

    with patch("app.api.v1.enrollment.get_email_provider", return_value=mock_provider):
        await client.post(f"/api/v1/e/{slug}/otp/request", json={
            "name": "Alice", "email": "alice-attempts@example.com",
        })

    # Wrong code twice
    for _ in range(2):
        await client.post(f"/api/v1/e/{slug}/otp/verify", json={
            "name": "Alice", "email": "alice-attempts@example.com", "code": "000000",
        })

    test_session.expire_all()
    result = await test_session.execute(
        select(EnrollmentOTP).where(EnrollmentOTP.email == "alice-attempts@example.com")
    )
    otp = result.scalar_one_or_none()
    assert otp is not None
    assert otp.attempts == 2


@pytest.mark.asyncio
async def test_otp_verify_locked_after_max_attempts(client: AsyncClient, test_session):
    """After OTP_MAX_ATTEMPTS wrong guesses, the code should be locked out."""
    from app.config import settings

    _headers, slug = await _register_and_program(
        client, email="lockout@example.com", biz_name="Lockout Biz"
    )
    captured = []

    async def fake_send_otp(to_email, code, business_name):
        captured.append(code)

    mock_provider = MagicMock()
    mock_provider.send_otp = fake_send_otp

    with patch("app.api.v1.enrollment.get_email_provider", return_value=mock_provider):
        await client.post(f"/api/v1/e/{slug}/otp/request", json={
            "name": "Alice", "email": "alice-lockout@example.com",
        })

    # Exhaust all attempts with wrong codes
    for _ in range(settings.OTP_MAX_ATTEMPTS):
        r = await client.post(f"/api/v1/e/{slug}/otp/verify", json={
            "name": "Alice", "email": "alice-lockout@example.com", "code": "000000",
        })
        assert r.status_code == 400

    # Now try with the real code — should still be locked out
    assert captured
    r = await client.post(f"/api/v1/e/{slug}/otp/verify", json={
        "name": "Alice", "email": "alice-lockout@example.com", "code": captured[0],
    })
    assert r.status_code == 400
    assert "expired or invalid" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_otp_verify_expired_code_returns_400(client: AsyncClient, test_session):
    """Verify returns 400 when the OTP has expired."""
    _headers, slug = await _register_and_program(
        client, email="expired@example.com", biz_name="Expired Biz"
    )
    captured = []

    async def fake_send_otp(to_email, code, business_name):
        captured.append(code)

    mock_provider = MagicMock()
    mock_provider.send_otp = fake_send_otp

    with patch("app.api.v1.enrollment.get_email_provider", return_value=mock_provider):
        await client.post(f"/api/v1/e/{slug}/otp/request", json={
            "name": "Alice", "email": "alice-expired@example.com",
        })

    # Manually expire the OTP row
    test_session.expire_all()
    result = await test_session.execute(
        select(EnrollmentOTP).where(EnrollmentOTP.email == "alice-expired@example.com")
    )
    otp = result.scalar_one()
    otp.expires_at = datetime.utcnow() - timedelta(minutes=1)
    test_session.add(otp)
    await test_session.commit()

    resp = await client.post(f"/api/v1/e/{slug}/otp/verify", json={
        "name": "Alice", "email": "alice-expired@example.com", "code": captured[0],
    })
    assert resp.status_code == 400
    assert "expired" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_otp_dedup_same_email_returns_same_customer_and_card(client: AsyncClient):
    """Two successful OTP enrollments with the same email return the same customer_id and card_id."""
    _headers, slug = await _register_and_program(
        client, email="dedup@example.com", biz_name="Dedup Biz"
    )
    resp1 = await _do_otp_flow(client, slug, email="dedup-user@example.com")
    assert resp1.status_code == 200
    d1 = resp1.json()

    resp2 = await _do_otp_flow(client, slug, email="dedup-user@example.com")
    assert resp2.status_code == 200
    d2 = resp2.json()

    assert d1["customer_id"] == d2["customer_id"]
    assert d1["card_id"] == d2["card_id"]
    assert d1["pass_serial"] == d2["pass_serial"]


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------

def _make_google_payload(email="guser@example.com", sub="google-sub-123", name="Google User", email_verified=True):
    return {
        "sub": sub,
        "email": email,
        "name": name,
        "email_verified": email_verified,
    }


@pytest.mark.asyncio
async def test_google_enroll_returns_enroll_response(client: AsyncClient):
    _headers, slug = await _register_and_program(
        client, email="gowner@example.com", biz_name="Google Biz"
    )
    payload = _make_google_payload()

    # Patch the thin helper function so we don't need the requests library installed.
    with patch("app.api.v1.enrollment._verify_google_token", return_value=payload):
        resp = await client.post(f"/api/v1/e/{slug}/google", json={
            "id_token": "fake-id-token",
        })

    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "guser@example.com"
    assert data["email_verified"] is True
    assert "pass_url" in data


@pytest.mark.asyncio
async def test_google_enroll_dedup_against_otp_customer(client: AsyncClient):
    """Google enrollment with same email as an OTP-enrolled customer returns same customer + populates google_sub."""
    _headers, slug = await _register_and_program(
        client, email="gdedup@example.com", biz_name="Google Dedup Biz"
    )
    # First: OTP enrollment
    otp_resp = await _do_otp_flow(client, slug, email="shared@example.com")
    assert otp_resp.status_code == 200
    otp_data = otp_resp.json()

    # Second: Google enrollment with same email
    payload = _make_google_payload(email="shared@example.com", sub="google-sub-xyz")

    with patch("app.api.v1.enrollment._verify_google_token", return_value=payload):
        g_resp = await client.post(f"/api/v1/e/{slug}/google", json={
            "id_token": "fake-id-token",
        })

    assert g_resp.status_code == 200
    g_data = g_resp.json()

    # Same customer_id and card_id
    assert g_data["customer_id"] == otp_data["customer_id"]
    assert g_data["card_id"] == otp_data["card_id"]


@pytest.mark.asyncio
async def test_google_enroll_email_not_verified_returns_401(client: AsyncClient):
    _headers, slug = await _register_and_program(
        client, email="gnotverif@example.com", biz_name="Google Not Verified Biz"
    )
    payload = _make_google_payload(email_verified=False)

    with patch("app.api.v1.enrollment._verify_google_token", return_value=payload):
        resp = await client.post(f"/api/v1/e/{slug}/google", json={
            "id_token": "fake-id-token",
        })

    assert resp.status_code == 401
    assert "verified" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_google_enroll_invalid_token_returns_401(client: AsyncClient):
    _headers, slug = await _register_and_program(
        client, email="ginvalid@example.com", biz_name="Google Invalid Biz"
    )

    with patch("app.api.v1.enrollment._verify_google_token", side_effect=ValueError("bad token")):
        resp = await client.post(f"/api/v1/e/{slug}/google", json={
            "id_token": "invalid-token",
        })

    assert resp.status_code == 401
    assert "invalid" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# DB unique constraint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_customer_unique_constraint_business_email(test_session, client, auth_headers, program):
    """Inserting two customers with the same (business_id, email) raises IntegrityError."""
    from app.models.user import MerchantUser

    result = await test_session.execute(
        select(MerchantUser).where(MerchantUser.email == "owner@example.com")
    )
    user = result.scalar_one()
    business_id = user.business_id

    c1 = Customer(
        business_id=business_id,
        name="Alice",
        email="unique-test@example.com",
        email_verified=True,
        enrollment_channel="otp",
    )
    test_session.add(c1)
    await test_session.flush()

    c2 = Customer(
        business_id=business_id,
        name="Alice 2",
        email="unique-test@example.com",
        email_verified=True,
        enrollment_channel="otp",
    )
    test_session.add(c2)

    with pytest.raises(IntegrityError):
        await test_session.flush()

    await test_session.rollback()


# ---------------------------------------------------------------------------
# Enrollment landing page — HTML
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrollment_landing_renders(client: AsyncClient):
    headers, slug = await _register_and_program(
        client, email="landing@example.com", biz_name="Landing Cafe"
    )
    resp = await client.get(f"/e/{slug}")
    assert resp.status_code == 200
    assert "Landing Cafe" in resp.text
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_enrollment_landing_contains_reward_description(client: AsyncClient):
    headers, slug = await _register_and_program(
        client, email="landing2@example.com", biz_name="Stamp Shop", stamps=5
    )
    resp = await client.get(f"/e/{slug}")
    assert resp.status_code == 200
    assert "Buy 5 get 1 free" in resp.text


@pytest.mark.asyncio
async def test_enrollment_landing_404_for_unknown_slug(client: AsyncClient):
    resp = await client.get("/e/totally-unknown-slug-xyz123")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_enrollment_landing_no_active_program(client: AsyncClient):
    reg = await client.post("/api/v1/auth/register", json={
        "email": "noprog@example.com",
        "password": "testpass123",
        "business_name": "No Programme Biz",
    })
    assert reg.status_code == 201
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}
    biz = await client.get("/api/v1/business", headers=headers)
    slug = biz.json()["slug"]

    resp = await client.get(f"/e/{slug}")
    assert resp.status_code == 200
    assert "not accepting" in resp.text.lower()


# ---------------------------------------------------------------------------
# enrollment-qr — keep existing behaviour
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enrollment_qr_returns_png_when_authed(client: AsyncClient):
    headers, slug = await _register_and_program(
        client, email="qrtest@example.com", biz_name="QR Test Biz"
    )
    resp = await client.get("/api/v1/enrollment-qr", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_enrollment_qr_returns_401_without_auth(client: AsyncClient):
    resp = await client.get("/api/v1/enrollment-qr")
    assert resp.status_code == 401
