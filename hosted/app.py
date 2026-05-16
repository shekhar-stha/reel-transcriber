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
MAX_AUDIO_SECONDS = int(os.environ.get("MAX_AUDIO_SECONDS", "300"))   # 5 min default
MAX_AUDIO_BYTES = int(os.environ.get("MAX_AUDIO_BYTES", "25000000"))  # 25 MB (OpenAI Whisper hard limit)
RATE_LIMIT_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "20"))
ACCESS_PASSWORD = os.environ.get("ACCESS_PASSWORD", "")  # if empty, no auth (BAD for prod)

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


def require_auth(request: Request, session: str | None = Cookie(None)):
    """If ACCESS_PASSWORD is set, require a valid session cookie."""
    if not ACCESS_PASSWORD:
        return
    if session not in _sessions:
        raise HTTPException(401, "Auth required")


def rate_limit(request: Request):
    """Simple per-IP hourly rate limit."""
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    now = time.time()
    bucket = _rate_buckets[ip]
    # drop entries older than an hour
    _rate_buckets[ip] = [t for t in bucket if now - t < 3600]
    if len(_rate_buckets[ip]) >= RATE_LIMIT_PER_HOUR:
        raise HTTPException(429, f"Rate limit exceeded ({RATE_LIMIT_PER_HOUR}/hour). Try again later.")
    _rate_buckets[ip].append(now)


def probe_video(url: str) -> dict:
    """Use yt-dlp metadata-only mode to check duration BEFORE downloading. Cheap."""
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
async def transcribe(
    req: TranscribeRequest,
    request: Request,
    _auth=Depends(require_auth),
):
    rate_limit(request)

    url = req.url.strip()
    if not url:
        raise HTTPException(400, "URL is required")
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "URL must start with http:// or https://")

    # 1. Check duration BEFORE spending money
    info = probe_video(url)
    duration = info["duration"]
    if duration > MAX_AUDIO_SECONDS:
        raise HTTPException(
            400,
            f"Video is too long ({int(duration)}s). Max allowed: {MAX_AUDIO_SECONDS}s ({MAX_AUDIO_SECONDS // 60} min). "
            "This limit protects your OpenAI budget."
        )

    tmp_dir = tempfile.mkdtemp()
    output_template = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}],
        "quiet": True,
        "no_warnings": True,
        # Hard limits to prevent abuse
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

    # 2. Double-check file size before sending to OpenAI
    size = audio_file.stat().st_size
    if size > MAX_AUDIO_BYTES:
        audio_file.unlink(missing_ok=True)
        raise HTTPException(400, f"Audio too large ({size // 1_000_000} MB). Max: {MAX_AUDIO_BYTES // 1_000_000} MB.")

    try:
        with open(audio_file, "rb") as f:
            result = client().audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
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
    return {"ok": True, "auth_enabled": bool(ACCESS_PASSWORD)}


# ---- Login ----

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
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Login - Reel Transcriber</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #0a0a0a; color: #e5e5e5;
       min-height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; }}
.box {{ background: #1a1a1a; padding: 2rem; border-radius: 12px; border: 1px solid #333; width: 360px; }}
h1 {{ color: #fff; margin: 0 0 0.5rem; font-size: 1.4rem; }}
p {{ color: #888; margin: 0 0 1.5rem; font-size: 0.9rem; }}
input {{ width: 100%; padding: 0.75rem 1rem; background: #0a0a0a; border: 1px solid #333; border-radius: 8px;
         color: #fff; font-size: 1rem; margin-bottom: 0.75rem; outline: none; }}
input:focus {{ border-color: #d97706; }}
button {{ width: 100%; padding: 0.75rem; background: #d97706; color: #000; border: none; border-radius: 8px;
          font-size: 1rem; font-weight: 600; cursor: pointer; }}
.error {{ color: #ef4444; font-size: 0.85rem; margin-bottom: 0.75rem; }}
</style></head><body><div class="box">
<h1>Reel Transcriber</h1><p>Enter the team password to continue.</p>
{err_html}
<form method="POST" action="/login">
<input type="password" name="password" placeholder="Password" autofocus required>
<button type="submit">Sign in</button>
</form></div></body></html>"""


@app.get("/", response_class=HTMLResponse)
async def index(session: str | None = Cookie(None)):
    if ACCESS_PASSWORD and session not in _sessions:
        return HTMLResponse(_login_page())
    return (SCRIPT_DIR / "templates" / "index.html").read_text()
