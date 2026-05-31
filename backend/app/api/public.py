"""Public HTML page routes — no auth required.

Routes:
  GET /e/{business_slug}      — Enrollment landing page (mobile-first HTML)
  GET /pass/{pass_serial}     — Hosted stub wallet pass page (mobile-first HTML)
"""

import base64
import io

import qrcode
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db import get_session
from app.models.business import Business
from app.models.loyalty_card import LoyaltyCard
from app.models.program import RewardProgram

router = APIRouter()


def _html(title: str, body: str, bg: str = "#FFFFFF", fg: str = "#000000") -> str:
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
</head>
<body>
{body}
</body>
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


# ---------------------------------------------------------------------------
# GET /e/{business_slug} — Enrollment landing page
# ---------------------------------------------------------------------------

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
    {"<img src='" + business.logo_url + "' alt='logo' style='max-width:120px;margin-bottom:20px;border-radius:12px;'>" if business.logo_url else ""}
    <h1 style="font-size:1.8rem;font-weight:700;margin-bottom:8px;color:{label};">{business.name}</h1>
    <p style="font-size:1rem;margin-top:24px;opacity:0.7;">
      We are not accepting new enrollments right now.<br>Please check back soon!
    </p>
  </div>"""
        return HTMLResponse(content=_html(business.name, body, bg, fg))

    enroll_path = f"/api/v1/e/{business_slug}/enroll"

    body = f"""
  <div style="text-align:center;max-width:420px;width:100%;">
    {"<img src='" + business.logo_url + "' alt='logo' style='max-width:120px;margin-bottom:20px;border-radius:12px;'>" if business.logo_url else ""}
    <h1 style="font-size:1.8rem;font-weight:700;margin-bottom:8px;color:{label};">{business.name}</h1>
    <p style="font-size:1rem;margin-bottom:28px;opacity:0.8;">{program.reward_description}</p>

    <form id="enrollForm" onsubmit="return false"
          style="display:flex;flex-direction:column;gap:14px;text-align:left;">
      <label style="font-size:0.85rem;font-weight:600;color:{label};">Your Name
        <input name="name" type="text" required placeholder="Jane Smith"
               style="display:block;width:100%;margin-top:4px;padding:12px 14px;
                      border:1.5px solid {label};border-radius:10px;
                      background:transparent;color:{fg};font-size:1rem;outline:none;">
      </label>
      <label style="font-size:0.85rem;font-weight:600;color:{label};">Email or Phone
        <input name="contact" type="text" required placeholder="jane@example.com or +1 555 000"
               style="display:block;width:100%;margin-top:4px;padding:12px 14px;
                      border:1.5px solid {label};border-radius:10px;
                      background:transparent;color:{fg};font-size:1rem;outline:none;">
      </label>
      <label style="font-size:0.85rem;font-weight:600;color:{label};">Contact Type
        <select name="contact_type"
                style="display:block;width:100%;margin-top:4px;padding:12px 14px;
                       border:1.5px solid {label};border-radius:10px;
                       background:{bg};color:{fg};font-size:1rem;outline:none;">
          <option value="email">Email</option>
          <option value="phone">Phone</option>
        </select>
      </label>
      <button type="submit"
              style="margin-top:8px;padding:14px;border:none;border-radius:12px;
                     background:{label};color:{bg};font-size:1rem;font-weight:700;
                     cursor:pointer;">
        Join the programme
      </button>
    </form>

    <div id="msg" style="margin-top:20px;font-size:0.95rem;"></div>
  </div>

  <script>
    document.getElementById('enrollForm').addEventListener('submit', async function(e) {{
      e.preventDefault();
      const fd = new FormData(e.target);
      const payload = {{
        name: fd.get('name'),
        contact: fd.get('contact'),
        contact_type: fd.get('contact_type'),
        enrollment_channel: 'qr',
      }};
      const msg = document.getElementById('msg');
      try {{
        const res = await fetch('{enroll_path}', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/json'}},
          body: JSON.stringify(payload),
        }});
        if (res.ok) {{
          const data = await res.json();
          msg.innerHTML = '<strong>You\'re enrolled!</strong> <a href="' + data.pass_url + '">View your card &#8594;</a>';
          e.target.style.display = 'none';
        }} else {{
          const err = await res.json();
          msg.textContent = 'Error: ' + (err.detail || 'Something went wrong.');
        }}
      }} catch(ex) {{
        msg.textContent = 'Network error — please try again.';
      }}
    }});
  </script>"""

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
            slots_html += f'<span style="font-size:1.6rem;line-height:1;">&#9733;</span>'
        else:
            slots_html += f'<span style="font-size:1.6rem;line-height:1;opacity:0.3;">&#9734;</span>'

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

    return HTMLResponse(content=_html(biz_name, body, bg, fg))
