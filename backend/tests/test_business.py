import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_business(client: AsyncClient, auth_headers):
    response = await client.get("/api/v1/business", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Business"
    assert "slug" in data
    assert "id" in data
    assert "owner_user_id" in data


@pytest.mark.asyncio
async def test_get_business_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/business")
    assert response.status_code in (401, 403)  # HTTPBearer returns 403 or 401 depending on version


@pytest.mark.asyncio
async def test_update_business_name(client: AsyncClient, auth_headers):
    response = await client.patch("/api/v1/business", json={
        "name": "New Business Name",
    }, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Business Name"


@pytest.mark.asyncio
async def test_update_business_branding(client: AsyncClient, auth_headers):
    response = await client.patch("/api/v1/business", json={
        "bg_color": "#FF0000",
        "fg_color": "#FFFFFF",
        "label_color": "#0000FF",
    }, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["bg_color"] == "#FF0000"
    assert data["fg_color"] == "#FFFFFF"
    assert data["label_color"] == "#0000FF"


@pytest.mark.asyncio
async def test_update_business_logo(client: AsyncClient, auth_headers):
    response = await client.patch("/api/v1/business", json={
        "logo_url": "https://example.com/logo.png",
    }, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["logo_url"] == "https://example.com/logo.png"


@pytest.mark.asyncio
async def test_business_tenant_isolation(client: AsyncClient):
    """Two different businesses should each see only their own data."""
    # Register two different businesses
    resp1 = await client.post("/api/v1/auth/register", json={
        "email": "tenant1@example.com",
        "password": "password1",
        "business_name": "Tenant Business One",
    })
    assert resp1.status_code == 201
    token1 = resp1.json()["access_token"]

    resp2 = await client.post("/api/v1/auth/register", json={
        "email": "tenant2@example.com",
        "password": "password2",
        "business_name": "Tenant Business Two",
    })
    assert resp2.status_code == 201
    token2 = resp2.json()["access_token"]

    # Each can see their own business
    biz1 = await client.get("/api/v1/business", headers={"Authorization": f"Bearer {token1}"})
    assert biz1.status_code == 200
    assert biz1.json()["name"] == "Tenant Business One"

    biz2 = await client.get("/api/v1/business", headers={"Authorization": f"Bearer {token2}"})
    assert biz2.status_code == 200
    assert biz2.json()["name"] == "Tenant Business Two"

    # Business IDs should be different
    assert biz1.json()["id"] != biz2.json()["id"]
