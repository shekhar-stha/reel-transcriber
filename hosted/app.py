"""Hosted version. Uses OpenAI Whisper API (no local model, no torch)."""
import os
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from openai import OpenAI
from pydantic import BaseModel

SCRIPT_DIR = Path(__file__).parent.resolve()
# Render mounts a persistent disk at /data when configured; fall back to local dir
DATA_DIR = Path("/data") if Path("/data").exists() and os.access("/data", os.W_OK) else SCRIPT_DIR
DB_PATH = DATA_DIR / "history.db"

app = FastAPI(title="Reel Transcriber")
_client = None


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


class TranscribeRequest(BaseModel):
    url: str


class TranscribeResponse(BaseModel):
    id: int
    transcript: str
    language: str


@app.post("/api/transcribe", response_model=TranscribeResponse)
async def transcribe(req: TranscribeRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "URL is required")

    tmp_dir = tempfile.mkdtemp()
    output_template = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise HTTPException(400, f"Failed to download reel: {e}")

    audio_file = next(
        (f for f in Path(tmp_dir).iterdir() if f.suffix in (".mp3", ".m4a", ".wav", ".webm", ".opus")),
        None,
    )
    if not audio_file:
        raise HTTPException(500, "Audio file not found after download")

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
async def list_history():
    with db() as conn:
        rows = conn.execute(
            "SELECT id, url, language, model, created_at, substr(transcript, 1, 120) as preview "
            "FROM history ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/history/{item_id}")
async def get_history_item(item_id: int):
    with db() as conn:
        row = conn.execute("SELECT * FROM history WHERE id = ?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    return dict(row)


@app.delete("/api/history/{item_id}")
async def delete_history_item(item_id: int):
    with db() as conn:
        conn.execute("DELETE FROM history WHERE id = ?", (item_id,))
    return {"ok": True}


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def index():
    return (SCRIPT_DIR / "templates" / "index.html").read_text()
