from app.config import settings
from app.services.email.console import ConsoleEmailProvider
from app.services.email.resend import ResendEmailProvider


def get_email_provider():
    """Return the configured email provider.

    Falls back to ConsoleEmailProvider when RESEND_API_KEY is not set,
    so the local dev workflow works without any external signup.
    """
    if settings.RESEND_API_KEY:
        return ResendEmailProvider()
    return ConsoleEmailProvider()
