import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.main import app
from app.db import get_session

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    TestSessionLocal = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    TestSessionLocal = sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_session():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# Helper fixtures for common setup patterns

@pytest_asyncio.fixture(scope="function")
async def registered_user(client: AsyncClient):
    """Register a user and return tokens + credentials."""
    response = await client.post("/api/v1/auth/register", json={
        "email": "owner@example.com",
        "password": "testpassword123",
        "business_name": "Test Business",
    })
    assert response.status_code == 201
    data = response.json()
    return {
        "email": "owner@example.com",
        "password": "testpassword123",
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
    }


@pytest_asyncio.fixture(scope="function")
async def auth_headers(registered_user):
    """Return authorization headers for the registered user."""
    return {"Authorization": f"Bearer {registered_user['access_token']}"}


@pytest_asyncio.fixture(scope="function")
async def program(client: AsyncClient, auth_headers):
    """Create a reward program and return it."""
    response = await client.post("/api/v1/programs", json={
        "name": "Coffee Stamps",
        "type": "stamp",
        "stamps_required": 5,
        "reward_description": "Free coffee",
    }, headers=auth_headers)
    assert response.status_code == 201
    return response.json()


@pytest_asyncio.fixture(scope="function")
async def loyalty_card(client: AsyncClient, auth_headers, program, test_session):
    """Create a loyalty card directly in the DB and return it."""
    import secrets
    import uuid
    from datetime import datetime
    from app.models.customer import Customer
    from app.models.loyalty_card import LoyaltyCard, WalletPlatform, CardStatus
    from app.models.user import MerchantUser
    from sqlmodel import select

    # Get the business_id from the registered user
    result = await test_session.execute(
        select(MerchantUser).where(MerchantUser.email == "owner@example.com")
    )
    user = result.scalar_one()
    business_id = user.business_id

    # Create a customer
    customer = Customer(
        business_id=business_id,
        name="Test Customer",
        email="customer@example.com",
        email_verified=True,
        enrolled_at=datetime.utcnow(),
        enrollment_channel="web",
    )
    test_session.add(customer)
    await test_session.flush()

    # Create a loyalty card
    card = LoyaltyCard(
        business_id=business_id,
        customer_id=customer.id,
        program_id=program["id"],
        barcode_token=secrets.token_urlsafe(32),
        pass_serial=str(uuid.uuid4()),
        wallet_platform=WalletPlatform.stub,
        status=CardStatus.active,
    )
    test_session.add(card)
    await test_session.commit()
    await test_session.refresh(card)

    return card
