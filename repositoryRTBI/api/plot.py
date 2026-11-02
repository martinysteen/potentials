"""plot.py - click-to-plot pages for the PotRank Google Sheet.

    https://innovia.dk/rtbi-api/plot/tunnel/<ticker>     page: the ticker's tunnel plot (SVG, 150 x 90 mm, click = fit window)

PotRank users are commenters, so the sheet cannot run a script for them; instead a HYPERLINK
column in PotRank > ALL opens this page in a browser tab:
    =HYPERLINK("https://innovia.dk/rtbi-api/plot/tunnel/"&ENCODEURL(A5); "plot")

Access: Google sign-in + the SAME email allowlist as the MCP server (RTBI_MCP_ALLOWED_EMAILS),
so there is one list of who may see Potentials data. The Google OAuth client is the MCP's
(GOOGLE_CLIENT_ID/SECRET from ../mcp/.env); its "Authorized redirect URIs" must include
REDIRECT_URI below. After sign-in a signed cookie (RTBI_PLOT_SESSION_KEY, api/.env) keeps the
user in for SESSION_DAYS; the allowlist is re-checked on every request, so removing an email
takes effect at once. Without the keys the /plot routes answer 503; the rest of the API is unaffected.

Thumbnails: tunnel/app/data/thumbs/all/<ticker>_<daynum>.svg (or .png from runs before 2026-11-02 evening), written by tunnel/run_tunnel.sh
(nightly fit + hourly intraday redraw); the newest daynum per ticker is served.
"""
import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import quote, urlencode

import httpx
from dotenv import dotenv_values
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

THUMB_DIR = Path("/home/sm/potentials/tunnel/app/data/thumbs/all")
STAMDATA = Path("/home/sm/potentials/repositoryRTBI/data/Stamdata.csv")
PREFIX = "/rtbi-api/plot"                       # as seen from the browser (Caddy strips /rtbi-api)
REDIRECT_URI = "https://innovia.dk/rtbi-api/plot/auth"
SESSION_DAYS = 30
TICKER_RE = re.compile(r"^[A-Za-z0-9.^=&\-]{1,24}$")    # also keeps glob characters out of the file lookup

_mcp_env = dotenv_values(Path(__file__).resolve().parent.parent / "mcp" / ".env")
CLIENT_ID = _mcp_env.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = _mcp_env.get("GOOGLE_CLIENT_SECRET")
ALLOWED = {e.strip().lower() for e in (_mcp_env.get("RTBI_MCP_ALLOWED_EMAILS") or "").split(",") if e.strip()}
SESSION_KEY = (os.environ.get("RTBI_PLOT_SESSION_KEY") or "").encode()

router = APIRouter(prefix="/plot")


# --------------------------------------------------------------------------- #
# signed cookies (stdlib HMAC; itsdangerous is not in potsystem_env)           #
# --------------------------------------------------------------------------- #

def _sign(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    mac = hmac.new(SESSION_KEY, body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{mac}"


def _unsign(value: str | None) -> dict | None:
    if not value or "." not in value:
        return None
    body, mac = value.rsplit(".", 1)
    if not hmac.compare_digest(mac, hmac.new(SESSION_KEY, body.encode(), hashlib.sha256).hexdigest()):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body))
    except ValueError:
        return None
    return payload if payload.get("exp", 0) > time.time() else None


def _configured():
    if not (CLIENT_ID and CLIENT_SECRET and SESSION_KEY and ALLOWED):
        raise HTTPException(503, "plot pages are not configured on this server")


def _user(request: Request) -> str | None:
    s = _unsign(request.cookies.get("plot_session"))
    email = (s or {}).get("email", "")
    return email if email in ALLOWED else None


def _login_redirect(request: Request) -> RedirectResponse:
    """Off to Google; the state cookie carries the CSRF token and where to return to."""
    state = secrets.token_urlsafe(24)
    nxt = quote(PREFIX + request.url.path.split("/plot", 1)[1], safe="/")    # url.path is decoded (^GSPC)
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(dict(
        client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, response_type="code",
        scope="openid email", state=state))
    r = RedirectResponse(url, status_code=302)
    r.set_cookie("plot_state", _sign({"state": state, "next": nxt, "exp": time.time() + 600}),
                 max_age=600, path=PREFIX, httponly=True, secure=True, samesite="lax")
    return r


MEDIA = {".svg": "image/svg+xml", ".png": "image/png"}


def _thumb(ticker: str) -> Path | None:
    """Newest <ticker>_<daynum>.svg (vector, current) or .png (older runs); svg wins a tie."""
    if not TICKER_RE.match(ticker):
        return None
    files = [f for f in THUMB_DIR.glob(f"{ticker}_*.*")
             if f.suffix in MEDIA and f.stem.rsplit("_", 1)[1].isdigit()]
    files.sort(key=lambda f: (int(f.stem.rsplit("_", 1)[1]), f.suffix == ".svg"))
    return files[-1] if files else None


def _name(ticker: str) -> str:
    """Company name from Stamdata (first column = ticker, column 'Name'); '' if unknown."""
    try:
        with open(STAMDATA, encoding="utf-8-sig") as f:
            head = f.readline().rstrip("\n").split(";")
            i = head.index("Name")
            for line in f:
                cells = line.rstrip("\n").split(";")
                if cells[0] == ticker:
                    return cells[i] if i < len(cells) else ""
    except (OSError, ValueError):
        pass
    return ""


# --------------------------------------------------------------------------- #
# routes                                                                      #
# --------------------------------------------------------------------------- #

@router.get("/auth")
def auth(request: Request, code: str = "", state: str = ""):
    _configured()
    st = _unsign(request.cookies.get("plot_state"))
    if not st or not code or not hmac.compare_digest(st.get("state", ""), state):
        return HTMLResponse("<p>Sign-in expired or invalid. Click the link in the sheet again.</p>", 400)
    tok = httpx.post("https://oauth2.googleapis.com/token", timeout=10, data=dict(
        code=code, client_id=CLIENT_ID, client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI, grant_type="authorization_code"))
    if tok.status_code != 200:
        return HTMLResponse("<p>Google sign-in failed. Try again.</p>", 400)
    # The id_token came straight from Google's token endpoint over TLS, so its claims can be
    # read without verifying the signature (Google's own guidance for this flow).
    claims = json.loads(base64.urlsafe_b64decode(tok.json()["id_token"].split(".")[1] + "=="))
    email = (claims.get("email") or "").lower()
    if not claims.get("email_verified") or email not in ALLOWED:
        return HTMLResponse(f"<p>Access denied for {html.escape(email or 'unknown user')}. "
                            f"Ask sm@innovia.dk to be added.</p>", 403)
    nxt = st.get("next", "")
    r = RedirectResponse(nxt if nxt.startswith(PREFIX + "/") else PREFIX + "/", status_code=302)
    r.set_cookie("plot_session", _sign({"email": email, "exp": time.time() + SESSION_DAYS * 86400}),
                 max_age=SESSION_DAYS * 86400, path=PREFIX, httponly=True, secure=True, samesite="lax")
    r.delete_cookie("plot_state", path=PREFIX)
    return r


@router.get("/tunnel/{ticker}")
def tunnel_page(ticker: str, request: Request):
    _configured()
    if not _user(request):
        return _login_redirect(request)
    f = _thumb(ticker)
    t = html.escape(ticker)
    if not f:
        return HTMLResponse(f"<p>No tunnel plot for {t}.</p>", 404)
    daynum = f.stem.rsplit("_", 1)[1]
    drawn = time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime))
    img = f"{PREFIX}/tunnel-img/{quote(ticker, safe='')}?d={daynum}-{int(f.stat().st_mtime)}"
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{t} tunnel</title>
<style>body{{font:13px Arial,sans-serif;margin:12px;color:#333}}
img{{width:150mm;max-width:100%;height:auto;display:block;cursor:zoom-in}}
img.fit{{width:100%;height:calc(100vh - 70px);object-fit:contain;object-position:left top;cursor:zoom-out}}
.s{{color:#888;font-size:11px;margin-top:4px}}</style></head>
<body><img src="{img}" alt="{t} tunnel" title="click: fit the window / back" onclick="this.classList.toggle('fit')">
<div>{t} &nbsp;{html.escape(_name(ticker))}</div>
<div class="s">daynum {daynum} &middot; drawn {drawn}</div></body></html>""",
                        headers={"Cache-Control": "private, no-cache"})


@router.get("/tunnel-img/{ticker}")
def tunnel_img(ticker: str, request: Request):
    _configured()
    if not _user(request):
        raise HTTPException(403, "sign in first")
    f = _thumb(ticker)
    if not f:
        raise HTTPException(404, "no plot")
    return FileResponse(f, media_type=MEDIA[f.suffix], headers={"Cache-Control": "private, max-age=3600"})
