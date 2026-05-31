import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class ResendEmailProvider:
    """Send OTP emails via the Resend API (https://resend.com)."""

    _API_URL = "https://api.resend.com/emails"

    async def send_otp(self, to_email: str, code: str, business_name: str) -> None:
        body = (
            f"Your verification code for {business_name} is: {code}. "
            "It expires in 10 minutes."
        )
        payload = {
            "from": settings.EMAIL_FROM,
            "to": [to_email],
            "subject": f"Your {business_name} verification code",
            "text": body,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                self._API_URL,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
        if resp.status_code not in (200, 201):
            logger.error(
                "Resend API error %s for %s: %s",
                resp.status_code,
                to_email,
                resp.text,
            )
            resp.raise_for_status()
