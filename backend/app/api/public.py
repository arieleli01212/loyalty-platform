"""Public HTML page routes — no auth required.

Routes:
  GET /e/{business_slug}                    — Enrollment landing page (mobile-first HTML)
  GET /pass/{pass_serial}                   — Hosted stub wallet pass page (mobile-first HTML)
  GET /pass/{pass_serial}/manifest.webmanifest — PWA web app manifest (JSON)
  GET /pass/{pass_serial}/icon-{size}.png   — Per-pass home-screen icon (PNG)
  GET /sw.js                                — Service worker (JS)
"""

import base64
import io
import json
import re

import httpx
import qrcode
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse, Response
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.db import get_session
from app.models.business import Business
from app.models.loyalty_card import LoyaltyCard
from app.models.program import RewardProgram

router = APIRouter()


def _html(
    title: str,
    body: str,
    bg: str = "#FFFFFF",
    fg: str = "#000000",
    extra_head: str = "",
    extra_body: str = "",
) -> str:
    """Wrap body content in a minimal mobile-first HTML shell."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="mobile-web-app-capable" content="yes">
  <title>{title}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: {bg};
      color: {fg};
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 24px 16px;
    }}
    a {{ color: inherit; }}
  </style>
{extra_head}</head>
<body>
{body}
{extra_body}</body>
</html>"""


def _qr_data_uri(data: str) -> str:
    """Generate a QR code PNG and return it as a base64 data URI."""
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _hex_to_rgb(hex_color: str) -> tuple:
    """Convert a hex color string (#RRGGBB or #RGB) to an (R, G, B) tuple."""
    hex_color = hex_color.strip()
    if not hex_color.startswith("#"):
        return (128, 128, 128)
    h = hex_color[1:]
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    if len(h) != 6:
        return (128, 128, 128)
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return (128, 128, 128)


def _make_icon_png(size: int, bg_color: str, text_color: str, initials: str) -> bytes:
    """Generate a square PNG icon with initials on a solid background color."""
    bg_rgb = _hex_to_rgb(bg_color)
    fg_rgb = _hex_to_rgb(text_color)
    img = Image.new("RGB", (size, size), bg_rgb)
    draw = ImageDraw.Draw(img)

    # Use Pillow default bitmap font — no font discovery needed.
    # Scale the font by loading the default and drawing at a proportional size.
    # Since the default font is fixed-size, we draw the text centered manually.
    try:
        # Try to load a truetype font at a size proportional to the icon.
        font_size = max(12, size // (2 if len(initials) > 1 else 1) - size // 6)
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(12, size // 3))
        except (OSError, IOError):
            font = ImageFont.load_default()

    # Get bounding box of text to centre it
    bbox = draw.textbbox((0, 0), initials, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2 - bbox[0]
    y = (size - text_h) // 2 - bbox[1]
    draw.text((x, y), initials, font=font, fill=fg_rgb)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read()


def _business_initials(name: str) -> str:
    """Return 1-2 uppercase initials from a business name."""
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][0].upper()
    return (words[0][0] + words[1][0]).upper()


# ---------------------------------------------------------------------------
# GET /sw.js — Service worker
# ---------------------------------------------------------------------------

# The service worker is defined as a plain string (NOT an f-string) to avoid
# any Python escape processing of the JS source. It is injected verbatim.
_SERVICE_WORKER_JS = r"""
const CACHE_NAME = "loyalty-pass-v1";

// On install: skip waiting so the new SW takes over immediately.
self.addEventListener("install", (event) => {
  self.skipWaiting();
});

// On activate: claim all clients and purge old caches.
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch: network-first strategy.
// On success: clone the response into the cache.
// On failure: serve from cache if available; otherwise propagate the error.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Only cache same-origin /pass/ requests and icons.
  const isCacheable =
    url.origin === self.location.origin &&
    (url.pathname.startsWith("/pass/") || url.pathname.includes("/icon-"));

  if (!isCacheable) return;

  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response && response.status === 200) {
          const toCache = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, toCache));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
"""


@router.get("/sw.js")
async def service_worker():
    """Service worker for the loyalty pass PWA.

    Served at the root so its default scope covers the entire origin.
    The pass page sets its registration scope explicitly to /pass/ and
    this endpoint returns the Service-Worker-Allowed header permitting that.
    """
    return Response(
        content=_SERVICE_WORKER_JS,
        media_type="application/javascript",
        headers={
            # Allow the SW (served at /) to control /pass/ scope.
            "Service-Worker-Allowed": "/",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


# ---------------------------------------------------------------------------
# GET /pass/{pass_serial}/manifest.webmanifest — PWA web app manifest
# ---------------------------------------------------------------------------

@router.get("/pass/{pass_serial}/manifest.webmanifest")
async def pass_manifest(
    pass_serial: str,
    session: AsyncSession = Depends(get_session),
):
    """Return a per-pass Web App Manifest so the customer can install it to their home screen."""
    result = await session.execute(
        select(LoyaltyCard).where(LoyaltyCard.pass_serial == pass_serial)
    )
    card = result.scalar_one_or_none()
    if not card:
        return Response(content='{"error":"not found"}', status_code=404, media_type="application/manifest+json")

    biz_result = await session.execute(select(Business).where(Business.id == card.business_id))
    business = biz_result.scalar_one_or_none()

    biz_name = business.name if business else "Loyalty Card"
    bg_color = (business.bg_color if business else None) or "#1C1C1E"

    short_name = biz_name if len(biz_name) <= 12 else biz_name[:12].rstrip()

    manifest = {
        "name": biz_name,
        "short_name": short_name,
        "start_url": f"/pass/{pass_serial}",
        "scope": "/pass/",
        "display": "standalone",
        "theme_color": bg_color,
        "background_color": bg_color,
        "icons": [
            {
                "src": f"/pass/{pass_serial}/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": f"/pass/{pass_serial}/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable",
            },
        ],
    }

    return Response(
        content=json.dumps(manifest),
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ---------------------------------------------------------------------------
# GET /pass/{pass_serial}/icon-{size}.png — Per-pass home-screen icon
# ---------------------------------------------------------------------------

_ALLOWED_ICON_SIZES = {180, 192, 512}


@router.get("/pass/{pass_serial}/icon-{size}.png")
async def pass_icon(
    pass_serial: str,
    size: int,
    session: AsyncSession = Depends(get_session),
):
    """Return a PNG icon for the given pass at the requested size.

    If the business has a logo_url, we download and resize it.
    If that fails for any reason, we fall back to a generated placeholder
    with the business initials on a bg_color background.
    Never raises 5xx — always returns a valid PNG.
    """
    # Guard against absurd sizes.
    if size not in _ALLOWED_ICON_SIZES:
        # Clamp to nearest allowed size rather than 404-ing.
        size = min(_ALLOWED_ICON_SIZES, key=lambda s: abs(s - size))

    result = await session.execute(
        select(LoyaltyCard).where(LoyaltyCard.pass_serial == pass_serial)
    )
    card = result.scalar_one_or_none()

    if card:
        biz_result = await session.execute(select(Business).where(Business.id == card.business_id))
        business = biz_result.scalar_one_or_none()
    else:
        business = None

    bg_color = (business.bg_color if business else None) or "#1C1C1E"
    label_color = (business.label_color if business else None) or "#FFD700"
    biz_name = business.name if business else "Loyalty"

    png_bytes: bytes | None = None

    # Try to download and resize the logo if available.
    if business and business.logo_url:
        try:
            async with httpx.AsyncClient(timeout=5.0) as http:
                resp = await http.get(business.logo_url, follow_redirects=True)
            if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
                logo_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                # Resize maintaining aspect ratio, then paste onto bg-colored square.
                logo_img.thumbnail((size, size), Image.LANCZOS)
                bg_rgb = _hex_to_rgb(bg_color)
                canvas = Image.new("RGB", (size, size), bg_rgb)
                offset_x = (size - logo_img.width) // 2
                offset_y = (size - logo_img.height) // 2
                canvas.paste(logo_img, (offset_x, offset_y), mask=logo_img.split()[3] if logo_img.mode == "RGBA" else None)
                buf = io.BytesIO()
                canvas.save(buf, format="PNG")
                buf.seek(0)
                png_bytes = buf.read()
        except Exception:
            png_bytes = None  # fall through to placeholder

    # Fall back to generated placeholder.
    if png_bytes is None:
        initials = _business_initials(biz_name)
        png_bytes = _make_icon_png(size, bg_color, label_color, initials)

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ---------------------------------------------------------------------------
# GET /e/{business_slug} — Enrollment landing page
# ---------------------------------------------------------------------------

# The JS logic for the enrollment flow is defined as a *non-f-string* so that
# Python never processes any quotes or backslashes inside it.  Only the few
# dynamic values (slug, colors, google_client_id) are spliced in at well-
# defined injection points after the string is built.  This sidesteps the
# f-string apostrophe trap documented in CLAUDE.md.

_ENROLL_JS = r"""
(function() {
  var SLUG = "%%SLUG%%";
  var GOOGLE_CLIENT_ID = "%%GOOGLE_CLIENT_ID%%";

  // --- state ---
  var state = "picker";   // picker | email-form | otp-entry | success
  var savedName = "";
  var savedEmail = "";

  // --- element refs ---
  var picker   = document.getElementById("state-picker");
  var emailForm= document.getElementById("state-email");
  var otpForm  = document.getElementById("state-otp");
  var successEl= document.getElementById("state-success");
  var msgEl    = document.getElementById("msg");

  function showState(s) {
    state = s;
    picker.style.display   = (s === "picker")     ? "" : "none";
    emailForm.style.display= (s === "email-form") ? "" : "none";
    otpForm.style.display  = (s === "otp-entry")  ? "" : "none";
    successEl.style.display= (s === "success")    ? "" : "none";
    msgEl.textContent = "";
  }

  function setMsg(text, isError) {
    msgEl.textContent = text;
    msgEl.style.color = isError ? "#e53e3e" : "inherit";
  }

  // --- picker buttons ---
  var btnEmail  = document.getElementById("btn-use-email");
  var btnGoogle = document.getElementById("btn-google");
  if (btnEmail) {
    btnEmail.addEventListener("click", function() { showState("email-form"); });
  }

  // --- email form ---
  var emailFormEl = document.getElementById("form-email");
  if (emailFormEl) {
    emailFormEl.addEventListener("submit", async function(e) {
      e.preventDefault();
      var fd = new FormData(e.target);
      savedName  = fd.get("name");
      savedEmail = fd.get("email");
      setMsg("Sending code...", false);
      try {
        var res = await fetch("/api/v1/e/" + SLUG + "/otp/request", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({name: savedName, email: savedEmail}),
        });
        if (res.ok) {
          showState("otp-entry");
          var hint = document.getElementById("otp-hint");
          if (hint) hint.textContent = "We sent a code to " + savedEmail;
        } else {
          var err = await res.json();
          setMsg("Error: " + (err.detail || "Something went wrong."), true);
        }
      } catch(ex) {
        setMsg("Network error — please try again.", true);
      }
    });
  }

  // --- OTP form ---
  var otpFormEl = document.getElementById("form-otp");
  if (otpFormEl) {
    otpFormEl.addEventListener("submit", async function(e) {
      e.preventDefault();
      var fd = new FormData(e.target);
      var code = fd.get("code");
      setMsg("Verifying...", false);
      try {
        var res = await fetch("/api/v1/e/" + SLUG + "/otp/verify", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({name: savedName, email: savedEmail, code: code}),
        });
        if (res.ok) {
          var data = await res.json();
          showState("success");
          var link = document.getElementById("card-link");
          if (link) { link.href = data.pass_url; }
        } else {
          var err = await res.json();
          setMsg("Error: " + (err.detail || "Something went wrong."), true);
        }
      } catch(ex) {
        setMsg("Network error — please try again.", true);
      }
    });
  }

  // --- back links ---
  var backToPickerLinks = document.querySelectorAll(".back-to-picker");
  backToPickerLinks.forEach(function(el) {
    el.addEventListener("click", function(e) { e.preventDefault(); showState("picker"); });
  });

  // --- Google Sign-In ---
  if (GOOGLE_CLIENT_ID && btnGoogle) {
    // Load the GSI script dynamically only when needed.
    window.__googleCallback = async function(response) {
      setMsg("Signing in with Google...", false);
      try {
        var res = await fetch("/api/v1/e/" + SLUG + "/google", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({id_token: response.credential}),
        });
        if (res.ok) {
          var data = await res.json();
          showState("success");
          var link = document.getElementById("card-link");
          if (link) { link.href = data.pass_url; }
        } else {
          var err = await res.json();
          setMsg("Google sign-in failed: " + (err.detail || "Try again."), true);
          showState("picker");
        }
      } catch(ex) {
        setMsg("Network error — please try again.", true);
        showState("picker");
      }
    };

    btnGoogle.addEventListener("click", function() {
      // Initialize GSI once the library has loaded.
      function initAndPrompt() {
        google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: window.__googleCallback,
        });
        google.accounts.id.prompt();
      }
      if (typeof google !== "undefined" && google.accounts) {
        initAndPrompt();
      } else {
        var script = document.createElement("script");
        script.src = "https://accounts.google.com/gsi/client";
        script.onload = initAndPrompt;
        document.head.appendChild(script);
      }
    });
  } else if (btnGoogle) {
    btnGoogle.style.display = "none";
  }

  showState("picker");
})();
"""


@router.get("/e/{business_slug}", response_class=HTMLResponse)
async def enrollment_landing(
    business_slug: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Business).where(Business.slug == business_slug))
    business = result.scalar_one_or_none()

    if not business:
        body = """
  <div style="text-align:center;padding:40px 0;">
    <h1 style="font-size:1.5rem;margin-bottom:12px;">Business Not Found</h1>
    <p>The loyalty programme you are looking for does not exist.</p>
  </div>"""
        return HTMLResponse(
            content=_html("Not Found", body),
            status_code=404,
        )

    # Find active program
    prog_result = await session.execute(
        select(RewardProgram).where(
            RewardProgram.business_id == business.id,
            RewardProgram.active == True,  # noqa: E712
        )
    )
    program = prog_result.scalar_one_or_none()

    bg = business.bg_color or "#FFFFFF"
    fg = business.fg_color or "#000000"
    label = business.label_color or fg

    if not program:
        body = f"""
  <div style="text-align:center;max-width:420px;width:100%;">
    {"<img src=\"" + business.logo_url + "\" alt=\"logo\" style=\"max-width:120px;margin-bottom:20px;border-radius:12px;\">" if business.logo_url else ""}
    <h1 style="font-size:1.8rem;font-weight:700;margin-bottom:8px;color:{label};">{business.name}</h1>
    <p style="font-size:1rem;margin-top:24px;opacity:0.7;">
      We are not accepting new enrollments right now.<br>Please check back soon!
    </p>
  </div>"""
        return HTMLResponse(content=_html(business.name, body, bg, fg))

    # Escape values for safe injection into the JS template.
    # These are inserted into a JS string literal — we only allow safe chars.
    safe_slug = business_slug.replace('"', "").replace("\\", "")
    safe_google_client_id = (settings.GOOGLE_CLIENT_ID or "").replace('"', "").replace("\\", "")

    # Splice the dynamic values into the non-f-string JS block.
    enroll_js = (
        _ENROLL_JS
        .replace("%%SLUG%%", safe_slug)
        .replace("%%GOOGLE_CLIENT_ID%%", safe_google_client_id)
    )

    # Show/hide Google button based on whether GOOGLE_CLIENT_ID is configured.
    google_btn_display = "" if settings.GOOGLE_CLIENT_ID else "display:none;"

    logo_html = (
        '<img src="' + business.logo_url + '" alt="logo" '
        'style="max-width:120px;margin-bottom:20px;border-radius:12px;">'
        if business.logo_url else ""
    )

    body = f"""
  <div style="text-align:center;max-width:420px;width:100%;">
    {logo_html}
    <h1 style="font-size:1.8rem;font-weight:700;margin-bottom:8px;color:{label};">{business.name}</h1>
    <p style="font-size:1rem;margin-bottom:28px;opacity:0.8;">{program.reward_description}</p>

    <!-- state: picker -->
    <div id="state-picker" style="display:flex;flex-direction:column;gap:12px;">
      <button id="btn-google" type="button"
              style="{google_btn_display}padding:14px;border:2px solid {label};border-radius:12px;
                     background:transparent;color:{fg};font-size:1rem;font-weight:600;
                     cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;">
        <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
          <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
          <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
          <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
          <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
          <path fill="none" d="M0 0h48v48H0z"/>
        </svg>
        Sign in with Google
      </button>
      <button id="btn-use-email" type="button"
              style="padding:14px;border:2px solid {label};border-radius:12px;
                     background:{label};color:{bg};font-size:1rem;font-weight:700;
                     cursor:pointer;">
        Use email instead
      </button>
    </div>

    <!-- state: email-form -->
    <div id="state-email" style="display:none;text-align:left;">
      <form id="form-email" style="display:flex;flex-direction:column;gap:14px;">
        <label style="font-size:0.85rem;font-weight:600;color:{label};">Your Name
          <input name="name" type="text" required placeholder="Jane Smith" autocomplete="name"
                 style="display:block;width:100%;margin-top:4px;padding:12px 14px;
                        border:1.5px solid {label};border-radius:10px;
                        background:transparent;color:{fg};font-size:1rem;outline:none;">
        </label>
        <label style="font-size:0.85rem;font-weight:600;color:{label};">Email address
          <input name="email" type="email" required placeholder="jane@example.com" autocomplete="email"
                 style="display:block;width:100%;margin-top:4px;padding:12px 14px;
                        border:1.5px solid {label};border-radius:10px;
                        background:transparent;color:{fg};font-size:1rem;outline:none;">
        </label>
        <button type="submit"
                style="padding:14px;border:none;border-radius:12px;
                       background:{label};color:{bg};font-size:1rem;font-weight:700;
                       cursor:pointer;">
          Send verification code
        </button>
      </form>
      <p style="margin-top:12px;font-size:0.85rem;text-align:center;">
        <a href="#" class="back-to-picker" style="opacity:0.6;">&#8592; Back</a>
      </p>
    </div>

    <!-- state: otp-entry -->
    <div id="state-otp" style="display:none;text-align:left;">
      <p id="otp-hint" style="margin-bottom:16px;font-size:0.9rem;opacity:0.75;text-align:center;"></p>
      <form id="form-otp" style="display:flex;flex-direction:column;gap:14px;">
        <label style="font-size:0.85rem;font-weight:600;color:{label};">6-digit code
          <input name="code" type="text" inputmode="numeric" pattern="[0-9]{{6}}" maxlength="6"
                 required placeholder="123456" autocomplete="one-time-code"
                 style="display:block;width:100%;margin-top:4px;padding:12px 14px;
                        border:1.5px solid {label};border-radius:10px;
                        background:transparent;color:{fg};font-size:1.4rem;
                        letter-spacing:0.3em;text-align:center;outline:none;">
        </label>
        <button type="submit"
                style="padding:14px;border:none;border-radius:12px;
                       background:{label};color:{bg};font-size:1rem;font-weight:700;
                       cursor:pointer;">
          Verify &amp; join
        </button>
      </form>
      <p style="margin-top:12px;font-size:0.85rem;text-align:center;">
        <a href="#" class="back-to-picker" style="opacity:0.6;">&#8592; Back</a>
      </p>
    </div>

    <!-- state: success -->
    <div id="state-success" style="display:none;text-align:center;padding:24px 0;">
      <p style="font-size:1.1rem;font-weight:600;margin-bottom:16px;">
        &#127881; You&apos;re enrolled!
      </p>
      <a id="card-link" href="#"
         style="display:inline-block;padding:14px 28px;background:{label};
                color:{bg};border-radius:12px;font-weight:700;font-size:1rem;
                text-decoration:none;">
        View your card &#8594;
      </a>
    </div>

    <div id="msg" style="margin-top:16px;font-size:0.9rem;min-height:1.2em;"></div>
  </div>

  <script>{enroll_js}</script>"""

    return HTMLResponse(content=_html(business.name, body, bg, fg))


# ---------------------------------------------------------------------------
# GET /pass/{pass_serial} — Hosted stub wallet pass page
# ---------------------------------------------------------------------------

@router.get("/pass/{pass_serial}", response_class=HTMLResponse)
async def wallet_pass_page(
    pass_serial: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(LoyaltyCard).where(LoyaltyCard.pass_serial == pass_serial)
    )
    card = result.scalar_one_or_none()

    if not card:
        body = """
  <div style="text-align:center;padding:40px 0;">
    <h1 style="font-size:1.5rem;margin-bottom:12px;">Pass Not Found</h1>
    <p>This loyalty card does not exist or has been revoked.</p>
  </div>"""
        return HTMLResponse(content=_html("Pass Not Found", body), status_code=404)

    # Load business and program
    biz_result = await session.execute(select(Business).where(Business.id == card.business_id))
    business = biz_result.scalar_one_or_none()

    prog_result = await session.execute(select(RewardProgram).where(RewardProgram.id == card.program_id))
    program = prog_result.scalar_one_or_none()

    bg = (business.bg_color if business else None) or "#1C1C1E"
    fg = (business.fg_color if business else None) or "#FFFFFF"
    label = (business.label_color if business else None) or "#FFD700"
    biz_name = business.name if business else "Loyalty Card"
    reward_desc = program.reward_description if program else ""
    stamps_required = program.stamps_required if program else 10

    # Build stamp slots
    current = card.current_stamps
    slots_html = ""
    for i in range(stamps_required):
        filled = i < current
        if filled:
            slots_html += '<span style="font-size:1.6rem;line-height:1;">&#9733;</span>'
        else:
            slots_html += '<span style="font-size:1.6rem;line-height:1;opacity:0.3;">&#9734;</span>'

    rewards_banner = ""
    if card.rewards_available > 0:
        rewards_banner = f"""
    <div style="margin:16px 0;padding:10px 16px;background:{label};color:{bg};
                border-radius:10px;font-weight:700;font-size:0.95rem;text-align:center;">
      &#127873; {card.rewards_available} reward{"s" if card.rewards_available != 1 else ""} available!
    </div>"""

    # QR code from barcode_token
    qr_data_uri = _qr_data_uri(card.barcode_token)

    logo_html = ""
    if business and business.logo_url:
        logo_html = f'<img src="{business.logo_url}" alt="logo" style="max-width:80px;margin-bottom:12px;border-radius:10px;">'

    body = f"""
  <div style="max-width:360px;width:100%;border-radius:20px;
              background:{bg};border:1.5px solid {label};padding:24px 20px;
              box-shadow:0 8px 32px rgba(0,0,0,0.25);text-align:center;">
    {logo_html}
    <h1 style="font-size:1.4rem;font-weight:700;color:{label};margin-bottom:4px;">{biz_name}</h1>
    <p style="font-size:0.9rem;opacity:0.75;margin-bottom:20px;">{reward_desc}</p>

    <div style="margin-bottom:8px;color:{label};">
      <span style="font-size:2.2rem;font-weight:800;">{current}</span>
      <span style="font-size:1.1rem;opacity:0.7;"> / {stamps_required} stamps</span>
    </div>
    <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:6px;margin-bottom:20px;color:{label};">
      {slots_html}
    </div>

    {rewards_banner}

    <div style="margin-top:20px;">
      <img src="{qr_data_uri}" alt="Scan barcode"
           style="width:180px;height:180px;border-radius:12px;background:#fff;padding:4px;">
      <p style="font-size:0.75rem;opacity:0.55;margin-top:6px;">Show this QR to earn stamps</p>
    </div>
  </div>

  <p style="margin-top:20px;font-size:0.75rem;opacity:0.5;text-align:center;">
    Tap <strong>Share &rarr; Add to Home Screen</strong> to keep this card on your phone.
  </p>"""

    # PWA head tags — only injected on the pass page, not on enrollment/404 pages.
    extra_head = f"""  <link rel="manifest" href="/pass/{pass_serial}/manifest.webmanifest">
  <link rel="apple-touch-icon" sizes="180x180" href="/pass/{pass_serial}/icon-180.png">
  <meta name="apple-mobile-web-app-title" content="{biz_name}">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="theme-color" content="{bg}">
"""

    # Service worker registration — uses a plain (non-f) string for the JS body
    # to avoid Python processing backslashes or quotes inside the script.
    # Double quotes are used throughout to sidestep the f-string apostrophe trap.
    _sw_register_js = (
        'if ("serviceWorker" in navigator) {'
        '  navigator.serviceWorker.register("/sw.js", { scope: "/pass/" })'
        '    .catch(function(e) { console.warn("SW registration failed", e); });'
        '}'
    )
    extra_body = f"  <script>{_sw_register_js}</script>\n"

    return HTMLResponse(content=_html(biz_name, body, bg, fg, extra_head=extra_head, extra_body=extra_body))
