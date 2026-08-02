"""Transcribe the Xandrine playbook reels, grouped by creator, with stats.

Detects likely non-talking-head reels (very low speech density) and flags them.
Gentle pacing (delay between requests) to avoid Instagram rate-limiting.
Checkpoints after every reel.
"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
import whisper, yt_dlp

SCRIPT_DIR = Path(__file__).parent.resolve()
FFMPEG = SCRIPT_DIR / "bin" / "ffmpeg"
if FFMPEG.exists():
    os.environ["PATH"] = f"{FFMPEG.parent}{os.pathsep}{os.environ.get('PATH','')}"

WORKLIST = Path("/Users/shekhar/Claude Code/reel-analysis/xandrine_reels.json")
CHECKPOINT = Path("/Users/shekhar/Claude Code/reel-analysis/xandrine_progress.json")
COOKIES = Path("/Users/shekhar/Claude Code/reel-analysis/.ig_cookies.txt")
DELAY = 5  # seconds between reels

def process(rec, model):
    url = rec["url"]
    tmp = Path(tempfile.mkdtemp())
    try:
        opts = {"format":"bestaudio/best","outtmpl":str(tmp/"a.%(ext)s"),
                "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"128"}],
                "quiet":True,"no_warnings":True}
        if FFMPEG.exists():
            opts["ffmpeg_location"] = str(FFMPEG.parent)
        if COOKIES.exists():
            opts["cookiefile"] = str(COOKIES)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        audio = next((p for p in tmp.iterdir() if p.suffix in (".mp3",".m4a",".wav",".webm",".opus")), None)
        if not audio:
            rec["status"]="error"; rec["error"]="no audio"; return rec
        r = model.transcribe(str(audio), fp16=False)
        text = r["text"].strip()
        dur = info.get("duration",0) or 0
        rec["transcript"] = text
        rec["language"] = r.get("language","?")
        rec["uploader"] = info.get("uploader","") or ""
        rec["duration"] = dur
        rec["view_count"] = info.get("view_count")
        rec["like_count"] = info.get("like_count")
        rec["comment_count"] = info.get("comment_count")
        rec["upload_date"] = info.get("upload_date","")
        # Heuristic: talking-head = decent speech density (chars per second)
        density = (len(text)/dur) if dur else 0
        rec["talking_head"] = density >= 6 and len(text) >= 40
        rec["status"] = "ok"
    except Exception as e:
        msg = str(e).lower()
        rec["status"]="error"
        rec["error"] = ("rate-limited / login required"
                        if any(s in msg for s in ("login","empty media","rate","isn't available")) else str(e)[:150])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rec

def main():
    work = json.loads(WORKLIST.read_text())
    done = {}
    if CHECKPOINT.exists():
        for r in json.loads(CHECKPOINT.read_text()):
            done[r["code"]] = r
    print(f"{len(work)} reels; {len(done)} already done.")
    print("Loading Whisper 'small'...")
    model = whisper.load_model("small")
    results = []
    ok=err=0
    for i, rec in enumerate(work, 1):
        if done.get(rec["code"],{}).get("status")=="ok":
            results.append(done[rec["code"]]); ok+=1
            print(f"[{i}/{len(work)}] @{rec['handle']} {rec['code']} — cached ✓"); continue
        print(f"[{i}/{len(work)}] @{rec['handle']} {rec['code']}")
        out = process(dict(rec), model)
        results.append(out)
        if out["status"]=="ok":
            ok+=1
            th = "TH" if out.get("talking_head") else "non-TH"
            print(f"     ✓ {th} · {len(out.get('transcript',''))}c · {out.get('view_count')} views")
        else:
            err+=1; print(f"     ✗ {out['error']}")
        merged = {**done, **{r["code"]:r for r in results}}
        CHECKPOINT.write_text(json.dumps(list(merged.values()), indent=2, default=str))
        time.sleep(DELAY)
    print(f"\n✅ {ok} ok, {err} failed.")

if __name__ == "__main__":
    main()
