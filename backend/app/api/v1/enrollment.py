import io
import secrets
import uuid
from datetime import datetime

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.core.deps import get_current_user
from app.db import get_session
from app.models.business import Business
from app.models.customer import Customer
from app.models.loyalty_card import LoyaltyCard, WalletPlatform, CardStatus
from app.models.program import RewardProgram
from app.models.user import MerchantUser
from app.schemas.enrollment import EnrollRequest, EnrollResponse
from app.services.wallet.stub import StubWalletProvider

router = APIRouter()

_wallet_provider = StubWalletProvider()


@router.post("/e/{business_slug}/enroll", response_model=EnrollResponse)
async def enroll_customer(
    business_slug: str,
    body: EnrollRequest,
    session: AsyncSession = Depends(get_session),
):
    """Public enrollment endpoint — creates a customer + loyalty card for the given business."""
    # Resolve business by slug
    result = await session.execute(
        select(Business).where(Business.slug == business_slug)
    )
    business = result.scalar_one_or_none()
    if not business:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    # Find the active RewardProgram
    result = await session.execute(
        select(RewardProgram).where(
            RewardProgram.business_id == business.id,
            RewardProgram.active == True,  # noqa: E712
        )
    )
    program = result.scalar_one_or_none()
    if not program:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Business has no active reward program",
        )

    # Create customer
    customer = Customer(
        business_id=business.id,
        name=body.name,
        contact=body.contact,
        contact_type=body.contact_type,
        enrolled_at=datetime.utcnow(),
        enrollment_channel=body.enrollment_channel or "qr",
    )
    session.add(customer)
    await session.flush()

    # Create loyalty card
    card = LoyaltyCard(
        business_id=business.id,
        customer_id=customer.id,
        program_id=program.id,
        pass_serial=str(uuid.uuid4()),
        barcode_token=secrets.token_urlsafe(32),
        wallet_platform=WalletPlatform.stub,
        current_stamps=0,
        status=CardStatus.active,
    )
    session.add(card)
    await session.commit()
    await session.refresh(card)
    await session.refresh(customer)

    # Get the pass artifact
    artifact = _wallet_provider.create_pass(card)

    return EnrollResponse(
        customer_id=customer.id,
        card_id=card.id,
        pass_serial=card.pass_serial,
        pass_url=artifact.url,
        current_stamps=card.current_stamps,
        stamps_required=program.stamps_required,
        reward_description=program.reward_description,
    )


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
        # A6 counter-card size (~105 x 148mm)
        page_width, page_height = A6
        c = rl_canvas.Canvas(pdf_buf, pagesize=A6)

        # Headline
        c.setFont("Helvetica-Bold", 14)
        c.drawCentredString(page_width / 2, page_height - 20 * mm, business.name)

        c.setFont("Helvetica", 11)
        c.drawCentredString(page_width / 2, page_height - 30 * mm, "Scan to join our rewards")

        # QR code centred
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
