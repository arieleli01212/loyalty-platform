from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "sqlite+aiosqlite:///./loyalty.db"
    SECRET_KEY: str = "changeme-use-a-real-secret-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    WALLET_PROVIDER: str = "stub"
    STAMP_THROTTLE_MINUTES: int = 2
    BASE_URL: str = "http://localhost:8000"
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000"]

    # Email / OTP settings
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "onboarding@resend.dev"
    OTP_EXPIRY_MINUTES: int = 10
    OTP_MAX_ATTEMPTS: int = 5

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""


settings = Settings()
