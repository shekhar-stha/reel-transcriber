"""Batch-transcribe + OCR text-hooks for reels from '1,000 Viral Hooks'.

For each reel:
  - download video
  - grab frames at 0.5/1.5/2.5/3.5s and OCR them (Apple Vision via bin/ocr) -> on-screen TEXT HOOK
  - extract audio + Whisper transcript (reused from checkpoint if already done)
Checkpoints to JSON after every reel so interruption never loses work.

Usage:
    python batch_hooks.py            # records 1..100
    python batch_hooks.py 1 1007     # all
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import whisper
import yt_dlp

SCRIPT_DIR = Path(__file__).parent.resolve()
FFMPEG_PATH = SCRIPT_DIR / "bin" / "ffmpeg"
OCR_BIN = SCRIPT_DIR / "bin" / "ocr"
if FFMPEG_PATH.exists():
    os.environ["PATH"] = f"{FFMPEG_PATH.parent}{os.pathsep}{os.environ.get('PATH', '')}"

DOC = "/Users/shekhar/Documents/Assets for building an AI/converted_md/1,000 Viral Hooks copy.md"
OUT_DIR = Path("/Users/shekhar/Claude Code/reel-analysis/hooks-batch")
OUT_DIR.mkdir(parents=True, exist_ok=True)
CHECKPOINT = OUT_DIR / "progress.json"
MODEL_SIZE = "small"
FRAME_TIMES = ["0.5", "1.5", "2.5", "3.5"]
COOKIES = OUT_DIR / ".ig_cookies.txt"  # optional Instagram auth (avoids rate limits)


def parse_records():
    lines = Path(DOC).read_text().splitlines()
    records, section = [], ""
    for line in lines:
        if line.startswith("## "):
            section = line[3:].strip(); continue
        m = re.match(r'^\|\s*(\d+)\s*\|(.+?)\|\s*<(.+?)>\s*\|\s*(\d+)\s*\|', line)
        if m:
            records.append({"num": int(m.group(1)), "section": section,
                            "hook": m.group(2).strip(), "link": m.group(3).strip(),
                            "page": m.group(4)})
    return records


def resolve_share(url):
    if "/share/" not in url:
        return url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.geturl()
    except Exception:
        return url


def ocr_image(path):
    try:
        out = subprocess.run([str(OCR_BIN), str(path)], capture_output=True, text=True, timeout=30)
        return out.stdout.strip()
    except Exception:
        return ""


def extract_text_hook(video, tmp):
    """Grab several early frames, OCR each, return the most complete on-screen text."""
    candidates = []
    for t in FRAME_TIMES:
        frame = tmp / f"f_{t}.jpg"
        try:
            subprocess.run([str(FFMPEG_PATH), "-y", "-ss", t, "-i", str(video),
                            "-frames:v", "1", "-q:v", "3", str(frame)],
                           check=True, capture_output=True, timeout=30)
        except Exception:
            continue
        if frame.exists():
            txt = ocr_image(frame)
            if txt:
                candidates.append(txt)
    if not candidates:
        return ""
    # Most complete = the one with the most characters (hook fully animated in)
    return max(candidates, key=len)


def process(rec, model):
    url = resolve_share(rec["link"])
    rec["resolved_link"] = url
    if "/share/" in url:
        rec["status"] = "error"; rec["error"] = "share link could not be resolved"; return rec

    have_transcript = rec.get("status") == "ok" and rec.get("transcript")

    tmp = Path(tempfile.mkdtemp())
    try:
        opts = {"format": "best[ext=mp4]/best", "outtmpl": str(tmp / "v.%(ext)s"),
                "quiet": True, "no_warnings": True}
        if FFMPEG_PATH.exists():
            opts["ffmpeg_location"] = str(FFMPEG_PATH.parent)
        if COOKIES.exists():
            opts["cookiefile"] = str(COOKIES)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        video = next((p for p in tmp.iterdir() if p.suffix in (".mp4", ".mkv", ".webm", ".mov")), None)
        if not video:
            rec["status"] = "error"; rec["error"] = "no video file"; return rec

        # TEXT HOOK via OCR
        rec["text_hook"] = extract_text_hook(video, tmp)

        # TRANSCRIPT (reuse if we already have it)
        if not have_transcript:
            audio = tmp / "a.mp3"
            subprocess.run([str(FFMPEG_PATH), "-y", "-i", str(video), "-vn",
                            "-acodec", "libmp3lame", "-q:a", "4", str(audio)],
                           check=True, capture_output=True, timeout=120)
            result = model.transcribe(str(audio), fp16=False)
            rec["transcript"] = result["text"].strip()
            rec["language"] = result.get("language", "?")

        rec["uploader"] = info.get("uploader", "") or rec.get("uploader", "")
        rec["duration"] = info.get("duration", 0) or rec.get("duration", 0)
        rec["like_count"] = info.get("like_count", rec.get("like_count"))
        rec["comment_count"] = info.get("comment_count", rec.get("comment_count"))
        rec["status"] = "ok"
        rec.pop("error", None)
    except Exception as e:
        msg = str(e)
        rec["status"] = "error"
        if any(s in msg.lower() for s in ("login", "empty media response", "rate", "isn't available")):
            rec["error"] = "requires Instagram login / unavailable"
        else:
            rec["error"] = msg[:200]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rec


def main():
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end = int(sys.argv[2]) if len(sys.argv) > 2 else 100

    records = parse_records()
    subset = [r for r in records if start <= r["num"] <= end]
    print(f"Parsed {len(records)}. Processing #{start}..#{end} ({len(subset)}).")

    done = {}
    if CHECKPOINT.exists():
        for r in json.loads(CHECKPOINT.read_text()):
            done[r["num"]] = r
        print(f"Checkpoint: {len(done)} records loaded.")

    print(f"Loading Whisper '{MODEL_SIZE}'...")
    model = whisper.load_model(MODEL_SIZE)

    results, ok, err = [], 0, 0
    for i, base in enumerate(subset, 1):
        prev = done.get(base["num"], {})
        # Skip only if fully done: has transcript AND text_hook already
        if prev.get("status") == "ok" and prev.get("transcript") and prev.get("text_hook") is not None:
            results.append(prev); ok += 1
            print(f"[{i}/{len(subset)}] #{base['num']} — complete ✓")
            continue
        # merge prior fields (keeps transcript if present)
        rec = {**base, **prev}
        print(f"[{i}/{len(subset)}] #{base['num']} {base['link'][:55]}")
        out = process(rec, model)
        results.append(out)
        if out["status"] == "ok":
            ok += 1
            th = (out.get("text_hook") or "").replace(chr(10), " / ")[:60]
            print(f"     ✓ hook:\"{th}\" · {len(out.get('transcript',''))}c transcript")
        else:
            err += 1
            print(f"     ✗ {out['error']}")
        merged = {**done, **{r["num"]: r for r in results}}
        CHECKPOINT.write_text(json.dumps(list(merged.values()), indent=2, default=str))

    print(f"\n✅ Done. {ok} ok, {err} failed.")


if __name__ == "__main__":
    main()
