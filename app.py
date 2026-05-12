import os
import tempfile
import uuid
from pathlib import Path

import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from openai import OpenAI
from pydantic import BaseModel

app = FastAPI(title="Reel Transcriber")

client = None


def get_client():
    global client
    if client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(500, "OPENAI_API_KEY not configured on the server")
        client = OpenAI(api_key=api_key)
    return client


class TranscribeRequest(BaseModel):
    url: str


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
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise HTTPException(400, f"Failed to download reel: {e}")

    audio_file = None
    for f in Path(tmp_dir).iterdir():
        if f.suffix in (".mp3", ".m4a", ".wav", ".webm", ".opus"):
            audio_file = f
            break

    if not audio_file or not audio_file.exists():
        raise HTTPException(500, "Audio file not found after download")

    try:
        with open(audio_file, "rb") as f:
            result = get_client().audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
            )
        transcript_text = result.text.strip()
        language = getattr(result, "language", "unknown")
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")
    finally:
        for f in Path(tmp_dir).iterdir():
            f.unlink(missing_ok=True)
        os.rmdir(tmp_dir)

    return TranscribeResponse(transcript=transcript_text, language=language)


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("templates/index.html").read_text()
