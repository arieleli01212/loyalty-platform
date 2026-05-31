import logging

logger = logging.getLogger(__name__)


class ConsoleEmailProvider:
    """Development fallback — prints the OTP to stdout/logs instead of sending email.

    Used automatically when RESEND_API_KEY is not configured. Safe to use in
    tests and local development without any external signup required.
    """

    async def send_otp(self, to_email: str, code: str, business_name: str) -> None:
        # NOTE: code is printed here intentionally (console provider only).
        # The production ResendEmailProvider never logs the code.
        logger.info(
            "[ConsoleEmailProvider] OTP for %s at %s: %s (expires in 10 min)",
            to_email,
            business_name,
            code,
        )
        print(
            f"[DEV EMAIL] To: {to_email} | Business: {business_name} | "
            f"Verification code: {code}"
        )
