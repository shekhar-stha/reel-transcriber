#!/usr/bin/env python3
"""
Offline reel transcriber. Usage:

    python transcribe.py <instagram-or-youtube-url> [--model base]

Models (smaller = faster, larger = more accurate):
    tiny    ~75 MB   fastest
    base    ~150 MB  good default
    small   ~500 MB  better accuracy
    medium  ~1.5 GB  great accuracy
    large   ~3 GB    best accuracy
"""
import argparse
import os
import sys
import tempfile
import uuid
from pathlib import Path

import whisper
import yt_dlp

SCRIPT_DIR = Path(__file__).parent.resolve()
FFMPEG_PATH = SCRIPT_DIR / "bin" / "ffmpeg"

# Make our bundled ffmpeg discoverable by yt-dlp and whisper
if FFMPEG_PATH.exists():
    os.environ["PATH"] = f"{FFMPEG_PATH.parent}{os.pathsep}{os.environ.get('PATH', '')}"


def download_audio(url: str, tmp_dir: str) -> str:
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
        "ffmpeg_location": str(FFMPEG_PATH.parent) if FFMPEG_PATH.exists() else None,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    for f in Path(tmp_dir).iterdir():
        if f.suffix in (".mp3", ".m4a", ".wav", ".webm", ".opus"):
            return str(f)
    raise RuntimeError("No audio file found after download")


def main():
    parser = argparse.ArgumentParser(description="Transcribe Instagram reels or any video URL")
    parser.add_argument("url", help="Reel or video URL")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large"])
    parser.add_argument("--out", help="Save transcript to this file (default: print to stdout)")
    args = parser.parse_args()

    tmp_dir = tempfile.mkdtemp()
    try:
        print(f"Downloading audio from {args.url}...", file=sys.stderr)
        audio_path = download_audio(args.url, tmp_dir)

        print(f"Loading Whisper '{args.model}' model (first time downloads ~{ {'tiny': '75MB', 'base': '150MB', 'small': '500MB', 'medium': '1.5GB', 'large': '3GB'}[args.model] })...", file=sys.stderr)
        model = whisper.load_model(args.model)

        print("Transcribing...", file=sys.stderr)
        result = model.transcribe(audio_path, fp16=False)

        transcript = result["text"].strip()
        if args.out:
            Path(args.out).write_text(transcript)
            print(f"Saved transcript to {args.out}", file=sys.stderr)
        else:
            print(transcript)
        print(f"\n[language: {result.get('language', 'unknown')}]", file=sys.stderr)
    finally:
        for f in Path(tmp_dir).iterdir():
            f.unlink(missing_ok=True)
        os.rmdir(tmp_dir)


if __name__ == "__main__":
    main()
