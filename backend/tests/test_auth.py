import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post("/api/v1/auth/register", json={
        "email": "newuser@example.com",
        "password": "password123",
        "business_name": "My Coffee Shop",
    })
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    payload = {
        "email": "dup@example.com",
        "password": "password123",
        "business_name": "Business One",
    }
    response1 = await client.post("/api/v1/auth/register", json=payload)
    assert response1.status_code == 201

    response2 = await client.post("/api/v1/auth/register", json={
        "email": "dup@example.com",
        "password": "password456",
        "business_name": "Business Two",
    })
    assert response2.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    # Register first
    await client.post("/api/v1/auth/register", json={
        "email": "logintest@example.com",
        "password": "testpassword",
        "business_name": "Login Test Biz",
    })

    # Login
    response = await client.post("/api/v1/auth/login", json={
        "email": "logintest@example.com",
        "password": "testpassword",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "wrongpw@example.com",
        "password": "correctpassword",
        "business_name": "Some Biz",
    })

    response = await client.post("/api/v1/auth/login", json={
        "email": "wrongpw@example.com",
        "password": "wrongpassword",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_email(client: AsyncClient):
    response = await client.post("/api/v1/auth/login", json={
        "email": "nobody@nowhere.com",
        "password": "whatever",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_refresh(client: AsyncClient, registered_user):
    response = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": registered_user["refresh_token"],
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    # Should not contain refresh_token in AccessTokenResponse
    assert "refresh_token" not in data


@pytest.mark.asyncio
async def test_token_refresh_invalid(client: AsyncClient):
    response = await client.post("/api/v1/auth/refresh", json={
        "refresh_token": "invalid.token.here",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_access_protected_with_valid_token(client: AsyncClient, auth_headers):
    response = await client.get("/api/v1/business", headers=auth_headers)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_access_protected_without_token(client: AsyncClient):
    response = await client.get("/api/v1/business")
    assert response.status_code in (401, 403)  # HTTPBearer returns 403 or 401 depending on version


@pytest.mark.asyncio
async def test_access_protected_with_invalid_token(client: AsyncClient):
    response = await client.get(
        "/api/v1/business",
        headers={"Authorization": "Bearer invalidtoken"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
