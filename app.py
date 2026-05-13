"""Local web UI for the reel transcriber. Run with: ./serve"""
import os
import tempfile
import uuid
from pathlib import Path

import whisper
import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

SCRIPT_DIR = Path(__file__).parent.resolve()
FFMPEG_PATH = SCRIPT_DIR / "bin" / "ffmpeg"
if FFMPEG_PATH.exists():
    os.environ["PATH"] = f"{FFMPEG_PATH.parent}{os.pathsep}{os.environ.get('PATH', '')}"

app = FastAPI(title="Reel Transcriber")
_model_cache = {}


def get_model(size: str):
    if size not in _model_cache:
        _model_cache[size] = whisper.load_model(size)
    return _model_cache[size]


class TranscribeRequest(BaseModel):
    url: str
    model: str = "base"


class TranscribeResponse(BaseModel):
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
        "ffmpeg_location": str(FFMPEG_PATH.parent) if FFMPEG_PATH.exists() else None,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise HTTPException(400, f"Failed to download: {e}")

    audio_file = next((f for f in Path(tmp_dir).iterdir() if f.suffix in (".mp3", ".m4a", ".wav", ".webm", ".opus")), None)
    if not audio_file:
        raise HTTPException(500, "Audio file not found after download")

    try:
        result = get_model(req.model).transcribe(str(audio_file), fp16=False)
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")
    finally:
        for f in Path(tmp_dir).iterdir():
            f.unlink(missing_ok=True)
        os.rmdir(tmp_dir)

    return TranscribeResponse(transcript=result["text"].strip(), language=result.get("language", "unknown"))


@app.get("/", response_class=HTMLResponse)
async def index():
    return (SCRIPT_DIR / "templates" / "index.html").read_text()
