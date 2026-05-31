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


settings = Settings()
