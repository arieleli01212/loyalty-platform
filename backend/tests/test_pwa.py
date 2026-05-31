"""Tests for PWA endpoints — manifest, icons, service worker."""

import json

import pytest
from httpx import AsyncClient
from sqlmodel import select

from app.models.loyalty_card import LoyaltyCard


# ---------------------------------------------------------------------------
# Helper — reused from test_enrollment.py pattern
# ---------------------------------------------------------------------------

async def _register_and_enroll(client: AsyncClient, *, email: str, biz_name: str):
    """Register a user, create a program, enroll a customer via OTP. Returns pass_serial."""
    from unittest.mock import AsyncMock, MagicMock, patch

    reg = await client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "testpass123",
        "business_name": biz_name,
    })
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    await client.post("/api/v1/programs", json={
        "name": "Test Programme",
        "type": "stamp",
        "stamps_required": 5,
        "reward_description": "Free item",
    }, headers=headers)

    biz_resp = await client.get("/api/v1/business", headers=headers)
    slug = biz_resp.json()["slug"]

    captured = []

    async def fake_send_otp(to_email, code, business_name):
        captured.append(code)

    mock_provider = MagicMock()
    mock_provider.send_otp = fake_send_otp

    with patch("app.api.v1.enrollment.get_email_provider", return_value=mock_provider):
        await client.post(f"/api/v1/e/{slug}/otp/request", json={
            "name": "Test Customer",
            "email": "customer@example.com",
        })

    enroll = await client.post(f"/api/v1/e/{slug}/otp/verify", json={
        "name": "Test Customer",
        "email": "customer@example.com",
        "code": captured[0],
    })
    assert enroll.status_code == 200
    return enroll.json()["pass_serial"]


# ---------------------------------------------------------------------------
# GET /sw.js
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sw_js_returns_javascript(client: AsyncClient):
    """Service worker endpoint returns JS content with correct content-type."""
    resp = await client.get("/sw.js")
    assert resp.status_code == 200
    assert "application/javascript" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_sw_js_contains_cache_name(client: AsyncClient):
    """Service worker contains expected cache name string."""
    resp = await client.get("/sw.js")
    assert "loyalty-pass-v1" in resp.text


@pytest.mark.asyncio
async def test_sw_js_has_service_worker_allowed_header(client: AsyncClient):
    """Service worker response includes Service-Worker-Allowed header."""
    resp = await client.get("/sw.js")
    assert "service-worker-allowed" in resp.headers


@pytest.mark.asyncio
async def test_sw_js_has_no_cache_header(client: AsyncClient):
    """Service worker is served with no-cache so browsers always revalidate."""
    resp = await client.get("/sw.js")
    cache_control = resp.headers.get("cache-control", "")
    assert "no-cache" in cache_control or "no-store" in cache_control


@pytest.mark.asyncio
async def test_sw_js_contains_fetch_listener(client: AsyncClient):
    """Service worker contains a fetch event listener (network-first strategy)."""
    resp = await client.get("/sw.js")
    assert "fetch" in resp.text
    assert "caches" in resp.text


# ---------------------------------------------------------------------------
# GET /pass/{serial}/manifest.webmanifest
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_manifest_returns_json(client: AsyncClient):
    """Manifest endpoint returns application/manifest+json with valid JSON."""
    serial = await _register_and_enroll(client, email="mfst1@example.com", biz_name="Manifest Biz")
    resp = await client.get(f"/pass/{serial}/manifest.webmanifest")
    assert resp.status_code == 200
    assert "manifest+json" in resp.headers["content-type"]
    data = resp.json()
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_manifest_contains_required_fields(client: AsyncClient):
    """Manifest contains name, start_url, display, theme_color, icons."""
    serial = await _register_and_enroll(client, email="mfst2@example.com", biz_name="Fields Biz")
    resp = await client.get(f"/pass/{serial}/manifest.webmanifest")
    assert resp.status_code == 200
    data = resp.json()
    assert "name" in data
    assert "short_name" in data
    assert data["start_url"] == f"/pass/{serial}"
    assert data["scope"] == "/pass/"
    assert data["display"] == "standalone"
    assert "theme_color" in data
    assert "background_color" in data
    assert "icons" in data


@pytest.mark.asyncio
async def test_manifest_icons_include_192_and_512(client: AsyncClient):
    """Manifest icons array includes 192x192 and 512x512 entries."""
    serial = await _register_and_enroll(client, email="mfst3@example.com", biz_name="Icon Sizes Biz")
    resp = await client.get(f"/pass/{serial}/manifest.webmanifest")
    data = resp.json()
    sizes = {icon["sizes"] for icon in data["icons"]}
    assert "192x192" in sizes
    assert "512x512" in sizes


@pytest.mark.asyncio
async def test_manifest_has_maskable_icon(client: AsyncClient):
    """At least one manifest icon has purpose containing 'maskable'."""
    serial = await _register_and_enroll(client, email="mfst4@example.com", biz_name="Maskable Biz")
    resp = await client.get(f"/pass/{serial}/manifest.webmanifest")
    data = resp.json()
    purposes = [icon.get("purpose", "") for icon in data["icons"]]
    assert any("maskable" in p for p in purposes)


@pytest.mark.asyncio
async def test_manifest_name_matches_business(client: AsyncClient):
    """Manifest name matches the registered business name."""
    serial = await _register_and_enroll(client, email="mfst5@example.com", biz_name="My Coffee Shop")
    resp = await client.get(f"/pass/{serial}/manifest.webmanifest")
    data = resp.json()
    assert data["name"] == "My Coffee Shop"


@pytest.mark.asyncio
async def test_manifest_404_for_unknown_serial(client: AsyncClient):
    """Manifest returns 404 for an unknown pass serial."""
    resp = await client.get("/pass/totally-fake-serial-xyz/manifest.webmanifest")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /pass/{serial}/icon-{size}.png
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_icon_192_returns_png(client: AsyncClient):
    """Icon endpoint for size 192 returns a PNG."""
    serial = await _register_and_enroll(client, email="icon1@example.com", biz_name="Icon Biz")
    resp = await client.get(f"/pass/{serial}/icon-192.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    # PNG magic bytes
    assert resp.content[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_icon_512_returns_png(client: AsyncClient):
    """Icon endpoint for size 512 returns a PNG."""
    serial = await _register_and_enroll(client, email="icon2@example.com", biz_name="Big Icon Biz")
    resp = await client.get(f"/pass/{serial}/icon-512.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_icon_180_returns_png(client: AsyncClient):
    """Icon endpoint for size 180 (apple-touch-icon) returns a PNG."""
    serial = await _register_and_enroll(client, email="icon3@example.com", biz_name="Apple Icon Biz")
    resp = await client.get(f"/pass/{serial}/icon-180.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_icon_has_long_cache_header(client: AsyncClient):
    """Icon response has a long cache-control max-age."""
    serial = await _register_and_enroll(client, email="icon4@example.com", biz_name="Cache Icon Biz")
    resp = await client.get(f"/pass/{serial}/icon-192.png")
    cache_control = resp.headers.get("cache-control", "")
    assert "max-age=86400" in cache_control


@pytest.mark.asyncio
async def test_icon_for_unknown_serial_still_returns_png(client: AsyncClient):
    """Icon endpoint for an unknown serial falls back gracefully and returns a PNG."""
    resp = await client.get("/pass/totally-unknown-serial-for-icon/icon-192.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# GET /pass/{serial} — pass page now includes PWA tags
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pass_page_has_manifest_link(client: AsyncClient):
    """Pass page HTML includes a <link rel=manifest> pointing to this pass's manifest."""
    serial = await _register_and_enroll(client, email="pwa1@example.com", biz_name="PWA Link Biz")
    resp = await client.get(f"/pass/{serial}")
    assert resp.status_code == 200
    assert f"/pass/{serial}/manifest.webmanifest" in resp.text
    assert 'rel="manifest"' in resp.text


@pytest.mark.asyncio
async def test_pass_page_has_apple_touch_icon(client: AsyncClient):
    """Pass page HTML includes an apple-touch-icon link for iOS home screen."""
    serial = await _register_and_enroll(client, email="pwa2@example.com", biz_name="Apple Touch Biz")
    resp = await client.get(f"/pass/{serial}")
    assert resp.status_code == 200
    assert "apple-touch-icon" in resp.text
    assert f"/pass/{serial}/icon-180.png" in resp.text


@pytest.mark.asyncio
async def test_pass_page_has_pwa_meta_tags(client: AsyncClient):
    """Pass page HTML includes apple-mobile-web-app-title and theme-color meta tags."""
    serial = await _register_and_enroll(client, email="pwa3@example.com", biz_name="Meta Tag Biz")
    resp = await client.get(f"/pass/{serial}")
    assert resp.status_code == 200
    assert "apple-mobile-web-app-title" in resp.text
    assert "Meta Tag Biz" in resp.text
    assert "theme-color" in resp.text


@pytest.mark.asyncio
async def test_pass_page_has_service_worker_registration(client: AsyncClient):
    """Pass page HTML includes a script to register the service worker."""
    serial = await _register_and_enroll(client, email="pwa4@example.com", biz_name="SW Register Biz")
    resp = await client.get(f"/pass/{serial}")
    assert resp.status_code == 200
    assert "serviceWorker" in resp.text
    assert "/sw.js" in resp.text


@pytest.mark.asyncio
async def test_enrollment_page_does_not_have_manifest_link(client: AsyncClient):
    """Enrollment page does NOT include a manifest link (PWA only on pass pages)."""
    reg = await client.post("/api/v1/auth/register", json={
        "email": "nopwa@example.com",
        "password": "testpass123",
        "business_name": "No PWA Biz",
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/programs", json={
        "name": "Prog",
        "type": "stamp",
        "stamps_required": 5,
        "reward_description": "Free item",
    }, headers=headers)
    biz_resp = await client.get("/api/v1/business", headers=headers)
    slug = biz_resp.json()["slug"]

    resp = await client.get(f"/e/{slug}")
    assert resp.status_code == 200
    # The enrollment page should not inject a PWA manifest link
    assert 'rel="manifest"' not in resp.text
    assert "manifest.webmanifest" not in resp.text


# ---------------------------------------------------------------------------
# Unit tests for helper functions
# ---------------------------------------------------------------------------

def test_hex_to_rgb_full():
    from app.api.public import _hex_to_rgb
    assert _hex_to_rgb("#1C1C1E") == (0x1C, 0x1C, 0x1E)


def test_hex_to_rgb_short():
    from app.api.public import _hex_to_rgb
    assert _hex_to_rgb("#FFF") == (0xFF, 0xFF, 0xFF)


def test_hex_to_rgb_invalid():
    from app.api.public import _hex_to_rgb
    assert _hex_to_rgb("not-a-color") == (128, 128, 128)


def test_business_initials_two_words():
    from app.api.public import _business_initials
    assert _business_initials("Coffee House") == "CH"


def test_business_initials_one_word():
    from app.api.public import _business_initials
    assert _business_initials("Starbucks") == "S"


def test_business_initials_empty():
    from app.api.public import _business_initials
    assert _business_initials("") == "?"


def test_business_initials_extra_spaces():
    from app.api.public import _business_initials
    assert _business_initials("  My   Cafe  ") == "MC"


def test_make_icon_png_returns_valid_png():
    from app.api.public import _make_icon_png
    data = _make_icon_png(64, "#1C1C1E", "#FFD700", "MC")
    assert data[:4] == b"\x89PNG"
