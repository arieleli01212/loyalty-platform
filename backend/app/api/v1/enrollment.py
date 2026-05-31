"""Enrollment API endpoints — verified two-method flow (OTP + Google OAuth).

Routes (all public, no JWT required):
  POST /e/{slug}/otp/request  — send a 6-digit OTP to the given email
  POST /e/{slug}/otp/verify   — verify the OTP and enroll / return existing card
  POST /e/{slug}/google       — verify a Google ID token and enroll / return card
  GET  /enrollment-qr         — generate a QR code for the enrollment URL (auth required)
"""

import io
import logging
import secrets
from datetime import datetime, timedelta

import qrcode
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.core.deps import get_current_user
from app.db import get_session
from app.models.business import Business
from app.models.enrollment_otp import EnrollmentOTP
from app.models.program import RewardProgram
from app.models.user import MerchantUser
from app.schemas.enrollment import (
    EnrollResponse,
    GoogleEnrollRequest,
    OtpRequestRequest,
    OtpRequestResponse,
    OtpVerifyRequest,
)
from app.services.email import get_email_provider
from app.services.enrollment import find_or_create_enrollment
from app.core.security import get_password_hash, verify_password

router = APIRouter()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve_business_and_program(
    slug: str,
    session: AsyncSession,
):
    """Return (Business, RewardProgram) for slug or raise 404/400."""
    biz_result = await session.execute(
        select(Business).where(Business.slug == slug)
    )
    business = biz_result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    prog_result = await session.execute(
        select(RewardProgram).where(
            RewardProgram.business_id == business.id,
            RewardProgram.active == True,  # noqa: E712
        )
    )
    program = prog_result.scalar_one_or_none()
    if not program:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Business has no active reward program",
        )

    return business, program


# ---------------------------------------------------------------------------
# POST /e/{slug}/otp/request
# ---------------------------------------------------------------------------

@router.post("/e/{business_slug}/otp/request", response_model=OtpRequestResponse)
async def otp_request(
    business_slug: str,
    body: OtpRequestRequest,
    session: AsyncSession = Depends(get_session),
):
    """Send a 6-digit OTP to the given email address.

    Always returns {"sent": true} — even if the email send fails — to avoid
    leaking whether a given email address is enrolled.
    """
    business, _program = await _resolve_business_and_program(business_slug, session)

    # Generate a 6-digit zero-padded code. Never put it in the response.
    code = str(secrets.randbelow(1_000_000)).zfill(6)
    code_hash = get_password_hash(code)
    expires_at = datetime.utcnow() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

    # Delete any existing OTP for this (business, email) pair so the customer
    # can re-request a fresh code without hitting the unique constraint.
    existing_result = await session.execute(
        select(EnrollmentOTP).where(
            EnrollmentOTP.business_id == business.id,
            EnrollmentOTP.email == body.email,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        await session.delete(existing)
        await session.flush()

    otp = EnrollmentOTP(
        business_id=business.id,
        email=body.email,
        code_hash=code_hash,
        expires_at=expires_at,
    )
    session.add(otp)
    await session.commit()

    # Send the OTP email — failures are logged but never surfaced to the client.
    try:
        provider = get_email_provider()
        await provider.send_otp(body.email, code, business.name)
    except Exception:
        logger.exception("Failed to send OTP email to %s", body.email)

    return OtpRequestResponse(sent=True)


# ---------------------------------------------------------------------------
# POST /e/{slug}/otp/verify
# ---------------------------------------------------------------------------

@router.post("/e/{business_slug}/otp/verify", response_model=EnrollResponse)
async def otp_verify(
    business_slug: str,
    body: OtpVerifyRequest,
    session: AsyncSession = Depends(get_session),
):
    """Verify the OTP and enroll the customer (or return their existing card)."""
    business, program = await _resolve_business_and_program(business_slug, session)

    # Load the OTP record
    otp_result = await session.execute(
        select(EnrollmentOTP).where(
            EnrollmentOTP.business_id == business.id,
            EnrollmentOTP.email == body.email,
        )
    )
    otp = otp_result.scalar_one_or_none()

    _invalid_error = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Code expired or invalid",
    )

    if otp is None:
        raise _invalid_error

    # Check expiry
    if datetime.utcnow() > otp.expires_at:
        raise _invalid_error

    # Check lockout
    if otp.attempts >= settings.OTP_MAX_ATTEMPTS:
        raise _invalid_error

    # Verify code
    if not verify_password(body.code, otp.code_hash):
        otp.attempts += 1
        session.add(otp)
        await session.commit()
        raise _invalid_error

    # Code is correct — delete the OTP row (one-time use)
    await session.delete(otp)
    await session.flush()

    return await find_or_create_enrollment(
        business,
        program,
        email=body.email,
        name=body.name,
        google_sub=None,
        channel="otp",
        session=session,
    )


# ---------------------------------------------------------------------------
# POST /e/{slug}/google
# ---------------------------------------------------------------------------

def _verify_google_token(id_token: str, client_id: str) -> dict:
    """Verify a Google ID token and return the payload dict.

    Isolated into its own function so tests can patch
    ``app.api.v1.enrollment._verify_google_token`` without needing the
    ``requests`` library installed (google-auth only needs requests for the
    transport layer, which isn't available in the lean venv).
    """
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests  # noqa: PLC0415

    return google_id_token.verify_oauth2_token(
        id_token,
        google_requests.Request(),
        client_id,
    )


@router.post("/e/{business_slug}/google", response_model=EnrollResponse)
async def google_enroll(
    business_slug: str,
    body: GoogleEnrollRequest,
    session: AsyncSession = Depends(get_session),
):
    """Verify a Google ID token and enroll the customer."""
    business, program = await _resolve_business_and_program(business_slug, session)

    # Verify the Google ID token.
    # The verify call is extracted into a helper so tests can patch it cleanly
    # without having to deal with the google.auth.transport.requests import.
    try:
        payload = _verify_google_token(body.id_token, settings.GOOGLE_CLIENT_ID)
    except Exception:
        logger.exception("Google token verification failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    if not payload.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google email not verified",
        )

    email = payload["email"]
    name = payload.get("name") or email
    google_sub = payload["sub"]

    return await find_or_create_enrollment(
        business,
        program,
        email=email,
        name=name,
        google_sub=google_sub,
        channel="google",
        session=session,
    )


# ---------------------------------------------------------------------------
# GET /enrollment-qr  — keep as-is
# ---------------------------------------------------------------------------

@router.get("/enrollment-qr")
async def enrollment_qr(
    format: str = "png",
    current_user: MerchantUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Returns a printable QR code pointing to the enrollment landing URL."""
    result = await session.execute(
        select(Business).where(Business.id == current_user.business_id)
    )
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    enrollment_url = f"{settings.BASE_URL}/e/{business.slug}"

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(enrollment_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    if format == "pdf":
        try:
            from reportlab.lib.pagesizes import A6
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas as rl_canvas
        except ImportError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="reportlab not installed",
            )

        # Save QR as PNG in memory
        png_buf = io.BytesIO()
        img.save(png_buf, format="PNG")
        png_buf.seek(0)

        # Build PDF
        pdf_buf = io.BytesIO()
        page_width, page_height = A6
        c = rl_canvas.Canvas(pdf_buf, pagesize=A6)

        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(page_width / 2, page_height - 20 * mm, business.name)

        c.setFont("Helvetica", 11)
        c.drawCentredString(page_width / 2, page_height - 30 * mm, "Scan to join our rewards")

        qr_size = 60 * mm
        qr_x = (page_width - qr_size) / 2
        qr_y = (page_height - qr_size) / 2 - 5 * mm

        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(png_buf), qr_x, qr_y, width=qr_size, height=qr_size)

        c.save()
        pdf_buf.seek(0)

        return FastAPIResponse(
            content=pdf_buf.read(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="enrollment-qr-{business.slug}.pdf"'},
        )

    # Default: PNG
    png_buf = io.BytesIO()
    img.save(png_buf, format="PNG")
    png_buf.seek(0)

    return FastAPIResponse(
        content=png_buf.read(),
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="enrollment-qr-{business.slug}.png"'},
    )
