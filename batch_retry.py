"""Slow-drip retry for rate-limited reels.

Re-attempts only the FAILED records from the checkpoint, pacing requests to
avoid tripping Instagram's rate limiter. Uses adaptive backoff: after a run of
consecutive failures it sleeps for a long cooldown, then resumes. Runs until
all recoverable reels are captured or it makes a full pass with zero progress.

Safe to run for many hours in the background; checkpoints after every reel.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import whisper
import yt_dlp

SCRIPT_DIR = Path(__file__).parent.resolve()
FFMPEG_PATH = SCRIPT_DIR / "bin" / "ffmpeg"
OCR_BIN = SCRIPT_DIR / "bin" / "ocr"
if FFMPEG_PATH.exists():
    os.environ["PATH"] = f"{FFMPEG_PATH.parent}{os.pathsep}{os.environ.get('PATH', '')}"

OUT_DIR = Path("/Users/shekhar/Claude Code/reel-analysis/hooks-batch")
CHECKPOINT = OUT_DIR / "progress.json"
COOKIES = OUT_DIR / ".ig_cookies.txt"
FRAME_TIMES = ["0.5", "1.5", "2.5", "3.5"]

# Pacing — longer rests let Instagram's IP rate-limit penalty actually decay
BASE_DELAY = 12          # seconds between attempts when things are healthy
COOLDOWN = 2400          # 40 min cooldown after a burst of failures
FAILS_BEFORE_COOLDOWN = 4
MAX_PASSES = 30          # safety cap


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
    cands = []
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
                cands.append(txt)
    return max(cands, key=len) if cands else ""


def process(rec, model):
    url = resolve_share(rec["link"])
    rec["resolved_link"] = url
    if "/share/" in url:
        rec["status"] = "error"; rec["error"] = "share link could not be resolved"; return rec, False
    if "tiktok.com" in url:
        rec["status"] = "error"; rec["error"] = "unsupported (tiktok short link)"; return rec, False

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
            rec["status"] = "error"; rec["error"] = "no video file"; return rec, False
        rec["text_hook"] = extract_text_hook(video, tmp)
        audio = tmp / "a.mp3"
        subprocess.run([str(FFMPEG_PATH), "-y", "-i", str(video), "-vn",
                        "-acodec", "libmp3lame", "-q:a", "4", str(audio)],
                       check=True, capture_output=True, timeout=120)
        result = model.transcribe(str(audio), fp16=False)
        rec["transcript"] = result["text"].strip()
        rec["language"] = result.get("language", "?")
        rec["uploader"] = info.get("uploader", "") or ""
        rec["duration"] = info.get("duration", 0) or 0
        rec["like_count"] = info.get("like_count")
        rec["comment_count"] = info.get("comment_count")
        rec["status"] = "ok"; rec.pop("error", None)
        return rec, True
    except Exception as e:
        msg = str(e).lower()
        rec["status"] = "error"
        rec["error"] = ("requires Instagram login / unavailable"
                        if any(s in msg for s in ("login", "empty media response", "rate", "isn't available"))
                        else str(e)[:200])
        return rec, False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def load():
    return {r["num"]: r for r in json.loads(CHECKPOINT.read_text())}


def save(by_num):
    CHECKPOINT.write_text(json.dumps(list(by_num.values()), indent=2, default=str))


def main():
    print("Loading Whisper 'small'...")
    model = whisper.load_model("small")

    for p in range(1, MAX_PASSES + 1):
        by_num = load()
        todo = [r for r in by_num.values()
                if r.get("status") != "ok"
                and "share link" not in (r.get("error") or "")
                and "tiktok" not in (r.get("error") or "")]
        if not todo:
            print("Nothing left to retry. All recoverable reels captured.")
            break
        print(f"\n===== PASS {p} — {len(todo)} reels to retry =====")
        recovered = 0
        consec_fail = 0
        for i, rec in enumerate(sorted(todo, key=lambda x: x["num"]), 1):
            out, ok = process(dict(rec), model)
            by_num[out["num"]] = out
            save(by_num)
            if ok:
                recovered += 1; consec_fail = 0
                th = (out.get("text_hook") or "").replace(chr(10), " / ")[:45]
                print(f"  [{i}/{len(todo)}] #{out['num']} ✓ recovered  \"{th}\"")
            else:
                consec_fail += 1
                print(f"  [{i}/{len(todo)}] #{out['num']} ✗ {out['error'][:40]}")
            # pacing
            if consec_fail >= FAILS_BEFORE_COOLDOWN:
                print(f"  …{consec_fail} consecutive blocks — cooling down {COOLDOWN//60} min")
                time.sleep(COOLDOWN)
                consec_fail = 0
            else:
                time.sleep(BASE_DELAY)
        print(f"Pass {p}: recovered {recovered}.")
        if recovered == 0:
            print("Zero progress this pass — Instagram still blocking. Long cooldown before next pass.")
            time.sleep(COOLDOWN)

    final = load()
    ok = sum(1 for r in final.values() if r.get("status") == "ok")
    print(f"\n✅ Retry finished. {ok}/{len(final)} captured.")


if __name__ == "__main__":
    main()
