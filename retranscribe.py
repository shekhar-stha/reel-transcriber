"""Re-transcribe specific reels with a better model."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import whisper
import yt_dlp

SCRIPT_DIR = Path(__file__).parent.resolve()
FFMPEG_PATH = SCRIPT_DIR / "bin" / "ffmpeg"
if FFMPEG_PATH.exists():
    os.environ["PATH"] = f"{FFMPEG_PATH.parent}{os.pathsep}{os.environ.get('PATH', '')}"

OUT_DIR = Path("/Users/shekhar/Claude Code/reel-analysis")
DATA = OUT_DIR / "data.json"
data = json.loads(DATA.read_text())

# Indices to retry (1-indexed)
RETRY = [1, 11]
# Use 'small' for big quality jump over base
MODEL_SIZE = "small"

print(f"Loading Whisper '{MODEL_SIZE}' model (~500 MB first time)...")
model = whisper.load_model(MODEL_SIZE)

for idx in RETRY:
    r = next(x for x in data if x["idx"] == idx)
    print(f"\n[Reel {idx}] {r['url']}")
    print(f"  Previous: {len(r['transcript'])} chars")

    tmp = Path(tempfile.mkdtemp())
    try:
        opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": str(tmp / "v.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
        if FFMPEG_PATH.exists():
            opts["ffmpeg_location"] = str(FFMPEG_PATH.parent)
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([r["url"]])
        video = next(p for p in tmp.iterdir() if p.suffix in (".mp4", ".webm", ".mkv"))
        result = model.transcribe(str(video), fp16=False, language="en")
        new_text = result["text"].strip()
        print(f"  New:      {len(new_text)} chars")
        r["transcript"] = new_text
        r["model_used"] = MODEL_SIZE
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

DATA.write_text(json.dumps(data, indent=2, default=str))
print(f"\n✅ data.json updated.")
