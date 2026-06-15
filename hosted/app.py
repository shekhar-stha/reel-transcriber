"""Hosted version. Uses OpenAI Whisper API (no local model, no torch)."""
import json
import os
import secrets
import sqlite3
import subprocess
import tempfile
import time
import uuid
from collections import defaultdict
from pathlib import Path

import yt_dlp
from fastapi import Cookie, Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from openai import OpenAI
from pydantic import BaseModel

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR = Path("/data") if Path("/data").exists() and os.access("/data", os.W_OK) else SCRIPT_DIR
DB_PATH = DATA_DIR / "history.db"

# ---- Limits & protections ----
MAX_AUDIO_SECONDS = int(os.environ.get("MAX_AUDIO_SECONDS", "300"))
MAX_AUDIO_BYTES = int(os.environ.get("MAX_AUDIO_BYTES", "25000000"))
RATE_LIMIT_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "20"))
ACCESS_PASSWORD = os.environ.get("ACCESS_PASSWORD", "")  # web login
API_TOKEN = os.environ.get("API_TOKEN", "")              # programmatic API access

app = FastAPI(title="Reel Transcriber")
_client = None
_rate_buckets: dict[str, list[float]] = defaultdict(list)
_sessions: set[str] = set()


def client() -> OpenAI:
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise HTTPException(500, "OPENAI_API_KEY is not configured on the server.")
        _client = OpenAI(api_key=key)
    return _client


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                transcript TEXT NOT NULL,
                language TEXT,
                model TEXT,
                created_at INTEGER NOT NULL
            )
        """)


init_db()


def has_bearer_auth(request: Request) -> bool:
    """Check for valid Bearer token in Authorization header."""
    if not API_TOKEN:
        return False
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return False
    return secrets.compare_digest(auth[7:].strip(), API_TOKEN)


def require_auth(request: Request, session: str | None = Cookie(None)):
    """Allow either Bearer token OR a valid session cookie."""
    if has_bearer_auth(request):
        return
    if not ACCESS_PASSWORD:
        return  # no auth configured at all
    if session not in _sessions:
        raise HTTPException(401, "Auth required")


def rate_limit(request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    now = time.time()
    bucket = _rate_buckets[ip]
    _rate_buckets[ip] = [t for t in bucket if now - t < 3600]
    if len(_rate_buckets[ip]) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(429, f"Rate limit exceeded ({RATE_LIMIT_PER_HOUR}/hour). Try again later.")
    _rate_buckets[ip].append(now)


def probe_video(url: str) -> dict:
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "duration": info.get("duration", 0) or 0,
                "title": info.get("title", ""),
                "filesize": info.get("filesize") or info.get("filesize_approx") or 0,
            }
    except Exception as e:
        raise HTTPException(400, f"Failed to read video info: {e}")


class TranscribeRequest(BaseModel):
    url: str


class TranscribeResponse(BaseModel):
    id: int
    transcript: str
    language: str


@app.post("/api/transcribe", response_model=TranscribeResponse)
async def transcribe(req: TranscribeRequest, request: Request, _auth=Depends(require_auth)):
    rate_limit(request)

    url = req.url.strip()
    if not url:
        raise HTTPException(400, "URL is required")
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "URL must start with http:// or https://")

    info = probe_video(url)
    duration = info["duration"]
    if duration > MAX_AUDIO_SECONDS:
        raise HTTPException(
            400,
            f"Video is too long ({int(duration)}s). Max allowed: {MAX_AUDIO_SECONDS}s ({MAX_AUDIO_SECONDS // 60} min)."
        )

    tmp_dir = tempfile.mkdtemp()
    output_template = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}],
        "quiet": True,
        "no_warnings": True,
        "max_filesize": MAX_AUDIO_BYTES,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise HTTPException(400, f"Failed to download: {e}")

    audio_file = next(
        (f for f in Path(tmp_dir).iterdir() if f.suffix in (".mp3", ".m4a", ".wav", ".webm", ".opus")),
        None,
    )
    if not audio_file:
        raise HTTPException(500, "Audio file not found after download")

    size = audio_file.stat().st_size
    if size > MAX_AUDIO_BYTES:
        audio_file.unlink(missing_ok=True)
        raise HTTPException(400, f"Audio too large ({size // 1_000_000} MB).")

    try:
        with open(audio_file, "rb") as f:
            result = client().audio.transcriptions.create(
                model="whisper-1", file=f, response_format="verbose_json",
            )
        transcript_text = (result.text or "").strip()
        language = getattr(result, "language", "unknown")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")
    finally:
        for f in Path(tmp_dir).iterdir():
            f.unlink(missing_ok=True)
        os.rmdir(tmp_dir)

    with db() as conn:
        cur = conn.execute(
            "INSERT INTO history (url, transcript, language, model, created_at) VALUES (?, ?, ?, ?, ?)",
            (url, transcript_text, language, "whisper-1", int(time.time())),
        )
        new_id = cur.lastrowid

    return TranscribeResponse(id=new_id, transcript=transcript_text, language=language)


@app.get("/api/history")
async def list_history(_auth=Depends(require_auth)):
    with db() as conn:
        rows = conn.execute(
            "SELECT id, url, language, model, created_at, substr(transcript, 1, 120) as preview "
            "FROM history ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/history/{item_id}")
async def get_history_item(item_id: int, _auth=Depends(require_auth)):
    with db() as conn:
        row = conn.execute("SELECT * FROM history WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@app.delete("/api/history/{item_id}")
async def delete_history_item(item_id: int, _auth=Depends(require_auth)):
    with db() as conn:
        conn.execute("DELETE FROM history WHERE id = ?", (item_id,))
    return {"ok": True}


@app.get("/healthz")
async def healthz():
    return {"ok": True, "auth_enabled": bool(ACCESS_PASSWORD), "api_token_enabled": bool(API_TOKEN)}


@app.post("/login")
async def login(password: str = Form(...)):
    if not ACCESS_PASSWORD:
        return RedirectResponse(url="/", status_code=303)
    if not secrets.compare_digest(password, ACCESS_PASSWORD):
        return HTMLResponse(_login_page(error="Wrong password."), status_code=401)
    token = secrets.token_urlsafe(32)
    _sessions.add(token)
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie("session", token, httponly=True, secure=True, samesite="lax", max_age=60 * 60 * 24 * 30)
    return resp


@app.get("/logout")
async def logout(session: str | None = Cookie(None)):
    if session:
        _sessions.discard(session)
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie("session")
    return resp


def _login_page(error: str = "") -> str:
    err_html = f'<div class="error">{error}</div>' if error else ""
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reel Transcriber - Sign in</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: radial-gradient(ellipse at top, #1a1109 0%, #0a0a0a 60%);
       color: #e5e5e5; min-height: 100vh; display: flex; flex-direction: column;
       align-items: center; justify-content: center; margin: 0; padding: 1.5rem; }}
.brand {{ text-align: center; margin-bottom: 2rem; }}
.brand .logo {{ display: inline-flex; align-items: center; justify-content: center;
               width: 56px; height: 56px; border-radius: 14px;
               background: linear-gradient(135deg, #d97706, #b45309);
               box-shadow: 0 8px 24px rgba(217, 119, 6, 0.25);
               font-size: 1.8rem; margin-bottom: 0.75rem; }}
.brand h1 {{ color: #fff; margin: 0; font-size: 1.5rem; font-weight: 700; }}
.brand .tag {{ color: #888; font-size: 0.9rem; margin-top: 0.35rem; }}
.box {{ background: rgba(26, 26, 26, 0.8); backdrop-filter: blur(10px);
        padding: 1.75rem; border-radius: 14px; border: 1px solid #2a2a2a;
        width: 100%; max-width: 380px;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4); }}
.box label {{ display: block; font-size: 0.8rem; color: #888; margin-bottom: 0.5rem;
              text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600; }}
.pw-wrap {{ position: relative; margin-bottom: 1rem; }}
input {{ width: 100%; padding: 0.85rem 2.6rem 0.85rem 1rem; background: #0a0a0a; border: 1px solid #333;
         border-radius: 9px; color: #fff; font-size: 1rem;
         outline: none; transition: border-color 0.15s; }}
input:focus {{ border-color: #d97706; }}
.toggle-pw {{ position: absolute; right: 0.5rem; top: 50%; transform: translateY(-50%);
              background: none; border: none; color: #666; cursor: pointer;
              padding: 0.4rem 0.55rem; border-radius: 6px;
              display: flex; align-items: center; justify-content: center; }}
.toggle-pw:hover {{ color: #d97706; background: rgba(217, 119, 6, 0.08); }}
button[type=submit] {{ width: 100%; padding: 0.85rem; background: #d97706; color: #000; border: none;
          border-radius: 9px; font-size: 1rem; font-weight: 600; cursor: pointer; }}
button[type=submit]:hover {{ background: #ea8b13; }}
.error {{ color: #ef4444; font-size: 0.85rem; margin-bottom: 0.75rem; padding: 0.6rem 0.8rem;
          background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 8px; }}
.footer {{ margin-top: 2rem; font-size: 0.8rem; color: #555; text-align: center; }}
.footer a {{ color: #888; text-decoration: none; border-bottom: 1px dotted #555; }}
.footer a:hover {{ color: #d97706; border-color: #d97706; }}
</style></head><body>
<div class="brand">
  <div class="logo">🎙️</div>
  <h1>Reel Transcriber</h1>
  <div class="tag">Turn any reel into text</div>
</div>
<div class="box">
{err_html}
<form method="POST" action="/login">
<label for="pw">Team password</label>
<div class="pw-wrap">
  <input id="pw" type="password" name="password" placeholder="••••••••••" autofocus required>
  <button type="button" class="toggle-pw" id="togglePw" aria-label="Show password">
    <svg id="eyeOpen" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
    <svg id="eyeOff" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="display:none"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
  </button>
</div>
<button type="submit">Sign in</button>
</form></div>
<div class="footer">Built by <a href="https://orcalynx.com" target="_blank" rel="noopener">Orcalynx</a></div>
<script>
(function() {{
  var btn = document.getElementById('togglePw');
  var input = document.getElementById('pw');
  var on = document.getElementById('eyeOpen');
  var off = document.getElementById('eyeOff');
  btn.addEventListener('click', function() {{
    var isPw = input.type === 'password';
    input.type = isPw ? 'text' : 'password';
    on.style.display = isPw ? 'none' : '';
    off.style.display = isPw ? '' : 'none';
    input.focus();
  }});
}})();
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index(session: str | None = Cookie(None)):
    if ACCESS_PASSWORD and session not in _sessions:
        return HTMLResponse(_login_page())
    return (SCRIPT_DIR / "templates" / "index.html").read_text()
