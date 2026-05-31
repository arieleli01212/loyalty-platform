from typing import Optional

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db import get_session
from app.models.user import MerchantUser
from app.schemas.scan import ScanRequest, ScanResponse
from app.services.loyalty import process_scan

router = APIRouter()


@router.post("", response_model=ScanResponse)
async def scan(
    body: ScanRequest,
    x_idempotency_key: Optional[str] = Header(default=None, alias="X-Idempotency-Key"),
    current_user: MerchantUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return await process_scan(
        barcode_token=body.barcode_token,
        action=body.action,
        current_user=current_user,
        session=session,
        idempotency_key=x_idempotency_key,
    )
