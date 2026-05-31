from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.config import settings


def _normalize_db_url(url: str) -> str:
    """Rewrite a vanilla Postgres URL to the async form SQLAlchemy expects.

    Hosted Postgres providers (Neon, Render, Heroku, etc.) hand out URLs in
    the form `postgresql://...?sslmode=require`. Those need two adjustments
    before they work with our async stack:
      1. Force the asyncpg dialect so SQLAlchemy doesn't try to import psycopg2.
      2. Translate libpq's `sslmode=` query param to asyncpg's `ssl=`.
    SQLite URLs and already-async Postgres URLs pass through unchanged.
    """
    if url.startswith("postgres://"):
        # Heroku-style alias
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if "sslmode=" in url:
        url = url.replace("sslmode=", "ssl=", 1)
    return url


DATABASE_URL = _normalize_db_url(settings.DATABASE_URL)

# Hosted Postgres (Neon free tier) auto-suspends after ~5 min of inactivity
# and Render's free web service sleeps after 15 min idle. When either side
# comes back, the pooled connections SQLAlchemy is holding are already dead,
# and the next query raises asyncpg's InterfaceError: connection is closed.
#
# pool_pre_ping issues a cheap SELECT 1 before handing out a connection and
# transparently reconnects if the ping fails. pool_recycle proactively
# replaces connections older than the timeout. Together they make the app
# robust against both ends going to sleep.
_is_sqlite = "sqlite" in DATABASE_URL

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=not _is_sqlite,
    pool_recycle=300 if not _is_sqlite else -1,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
