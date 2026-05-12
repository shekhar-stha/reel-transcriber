import os
import tempfile
import uuid
from pathlib import Path

import whisper
import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Reel Transcriber")

model = None


def get_model():
    global model
    if model is None:
        model_size = os.environ.get("WHISPER_MODEL", "base")
        model = whisper.load_model(model_size)
    return model


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
    audio_path = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.mp3")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": audio_path,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        raise HTTPException(400, f"Failed to download: {e}")

    final_path = audio_path
    if not os.path.exists(final_path):
        mp3_path = audio_path + ".mp3"
        if os.path.exists(mp3_path):
            final_path = mp3_path
        else:
            for f in Path(tmp_dir).iterdir():
                if f.suffix in (".mp3", ".m4a", ".wav", ".webm", ".opus"):
                    final_path = str(f)
                    break

    if not os.path.exists(final_path):
        raise HTTPException(500, "Audio file not found after download")

    try:
        result = get_model().transcribe(final_path)
    except Exception as e:
        raise HTTPException(500, f"Transcription failed: {e}")
    finally:
        for f in Path(tmp_dir).iterdir():
            f.unlink(missing_ok=True)
        os.rmdir(tmp_dir)

    return TranscribeResponse(
        transcript=result["text"].strip(),
        language=result.get("language", "unknown"),
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("templates/index.html").read_text()
