import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_program(client: AsyncClient, auth_headers):
    response = await client.post("/api/v1/programs", json={
        "name": "Loyalty Stamps",
        "type": "stamp",
        "stamps_required": 10,
        "reward_description": "Free item",
    }, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Loyalty Stamps"
    assert data["stamps_required"] == 10
    assert data["reward_description"] == "Free item"
    assert data["active"] is True
    assert "id" in data
    assert "business_id" in data


@pytest.mark.asyncio
async def test_list_programs(client: AsyncClient, auth_headers):
    # Create two programs
    await client.post("/api/v1/programs", json={
        "name": "Program A",
        "type": "stamp",
        "stamps_required": 5,
        "reward_description": "Reward A",
    }, headers=auth_headers)
    await client.post("/api/v1/programs", json={
        "name": "Program B",
        "type": "stamp",
        "stamps_required": 10,
        "reward_description": "Reward B",
    }, headers=auth_headers)

    response = await client.get("/api/v1/programs", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = {p["name"] for p in data}
    assert "Program A" in names
    assert "Program B" in names


@pytest.mark.asyncio
async def test_get_program(client: AsyncClient, auth_headers, program):
    response = await client.get(f"/api/v1/programs/{program['id']}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == program["id"]
    assert data["name"] == program["name"]


@pytest.mark.asyncio
async def test_get_program_not_found(client: AsyncClient, auth_headers):
    response = await client.get("/api/v1/programs/99999", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_program(client: AsyncClient, auth_headers, program):
    response = await client.patch(f"/api/v1/programs/{program['id']}", json={
        "name": "Updated Program Name",
        "stamps_required": 8,
    }, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Program Name"
    assert data["stamps_required"] == 8


@pytest.mark.asyncio
async def test_deactivate_program(client: AsyncClient, auth_headers, program):
    response = await client.patch(f"/api/v1/programs/{program['id']}", json={
        "active": False,
    }, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["active"] is False


@pytest.mark.asyncio
async def test_program_tenant_isolation(client: AsyncClient):
    """Users should not be able to see another tenant's programs."""
    # Register two tenants
    resp1 = await client.post("/api/v1/auth/register", json={
        "email": "p_tenant1@example.com",
        "password": "password1",
        "business_name": "P Tenant 1",
    })
    token1 = resp1.json()["access_token"]
    headers1 = {"Authorization": f"Bearer {token1}"}

    resp2 = await client.post("/api/v1/auth/register", json={
        "email": "p_tenant2@example.com",
        "password": "password2",
        "business_name": "P Tenant 2",
    })
    token2 = resp2.json()["access_token"]
    headers2 = {"Authorization": f"Bearer {token2}"}

    # Tenant 1 creates a program
    prog_resp = await client.post("/api/v1/programs", json={
        "name": "Tenant 1 Program",
        "type": "stamp",
        "stamps_required": 5,
        "reward_description": "Tenant 1 Reward",
    }, headers=headers1)
    prog_id = prog_resp.json()["id"]

    # Tenant 2 should NOT see tenant 1's program
    response = await client.get(f"/api/v1/programs/{prog_id}", headers=headers2)
    assert response.status_code == 404

    # Tenant 2's program list should be empty
    list_response = await client.get("/api/v1/programs", headers=headers2)
    assert list_response.status_code == 200
    assert list_response.json() == []
