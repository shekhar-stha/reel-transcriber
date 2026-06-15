"""Batch-analyze a list of Instagram reels.

For each URL:
  - download video + metadata via yt-dlp
  - capture a frame at ~1s (first text hook)
  - transcribe audio with local Whisper
  - write a markdown report
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import whisper
import yt_dlp

SCRIPT_DIR = Path(__file__).parent.resolve()
FFMPEG_PATH = SCRIPT_DIR / "bin" / "ffmpeg"
if FFMPEG_PATH.exists():
    os.environ["PATH"] = f"{FFMPEG_PATH.parent}{os.pathsep}{os.environ.get('PATH', '')}"

OUT_DIR = Path("/Users/shekhar/Claude Code/reel-analysis")
SHOTS_DIR = OUT_DIR / "screenshots"
SHOTS_DIR.mkdir(parents=True, exist_ok=True)
REPORT = OUT_DIR / "ANALYSIS.md"

# (note, url) pairs
REELS = [
    ("Annie", "https://www.instagram.com/reel/DYxCMBxhoYs/"),
    ("Gamifying type", "https://www.instagram.com/reel/DX_8bPhNzVX/"),
    ("Gamifying", "https://www.instagram.com/reel/DZDWtDyhP3l/"),
    ("Gamifying format", "https://www.instagram.com/reel/DYt_Xw2ow_f/"),
    ("Instead of manifestations - lessons from her life/business", "https://www.instagram.com/reel/DXE-Zdlji_v/"),
    ("Annie sent this", "https://www.instagram.com/reel/DY8mHAhOH_v/"),
    ("Annie's preferred content style / inspiration", "https://www.instagram.com/reel/DUOZc1_jahX/"),
    ("", "https://www.instagram.com/reel/DZNcrtdtCJT/"),
    ("", "https://www.instagram.com/reel/DWFeZ_hRmxc/"),
    ("", "https://www.instagram.com/reel/DWCDOaBgst1/"),
    ("", "https://www.instagram.com/reel/DW0W0cDDWP-/"),
    ("", "https://www.instagram.com/reel/DZVkRu1vu6Q/"),
    ("", "https://www.instagram.com/reel/DY-n6ijygDw/"),
    ("", "https://www.instagram.com/reel/DYsRkaVAK68/"),
]


def fmt_count(n):
    if n is None:
        return "—"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def process_one(idx, note, url, model):
    print(f"\n[{idx:02d}/{len(REELS)}] {url}")
    tmp = Path(tempfile.mkdtemp())
    try:
        # 1. Download video + grab metadata
        outtpl = str(tmp / "video.%(ext)s")
        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": outtpl,
            "quiet": True,
            "no_warnings": True,
        }
        if FFMPEG_PATH.exists():
            ydl_opts["ffmpeg_location"] = str(FFMPEG_PATH.parent)
        info = {}
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as e:
            print(f"   ✗ download failed: {e}")
            return {"idx": idx, "note": note, "url": url, "error": str(e)}

        video_file = next((p for p in tmp.iterdir() if p.suffix in (".mp4", ".mkv", ".webm", ".mov")), None)
        if not video_file:
            return {"idx": idx, "note": note, "url": url, "error": "no video file"}

        # 2. Screenshot at ~0.5s (catch first text hook)
        shot = SHOTS_DIR / f"reel_{idx:02d}_hook.jpg"
        try:
            subprocess.run(
                [str(FFMPEG_PATH), "-y", "-ss", "0.5", "-i", str(video_file),
                 "-frames:v", "1", "-q:v", "3", str(shot)],
                check=True, capture_output=True, timeout=30,
            )
            print(f"   ✓ screenshot: {shot.name}")
        except Exception as e:
            print(f"   ✗ screenshot failed: {e}")
            shot = None

        # 3. Transcribe
        try:
            result = model.transcribe(str(video_file), fp16=False)
            transcript = (result.get("text") or "").strip()
            language = result.get("language", "?")
            print(f"   ✓ transcript ({language}, {len(transcript)} chars)")
        except Exception as e:
            print(f"   ✗ transcribe failed: {e}")
            transcript = ""
            language = "?"

        return {
            "idx": idx,
            "note": note,
            "url": url,
            "title": info.get("title", "") or "",
            "uploader": info.get("uploader", "") or info.get("channel", "") or "",
            "duration": info.get("duration", 0) or 0,
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "comment_count": info.get("comment_count"),
            "upload_date": info.get("upload_date", ""),
            "screenshot": shot.name if shot else None,
            "transcript": transcript,
            "language": language,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print("Loading Whisper 'base' model...")
    model = whisper.load_model("base")

    results = []
    for i, (note, url) in enumerate(REELS, start=1):
        r = process_one(i, note, url, model)
        results.append(r)

    # Build markdown
    lines = []
    lines.append("# Reel Analysis\n")
    lines.append(f"_Generated {time.strftime('%Y-%m-%d')}. {len(results)} reels._\n")
    lines.append("## Summary table\n")
    lines.append("| # | Creator | Views | Likes | Comments | Duration | Note |")
    lines.append("|---|---------|-------|-------|----------|----------|------|")
    for r in results:
        if "error" in r:
            lines.append(f"| {r['idx']} | — | — | — | — | — | ERROR: {r['error']} |")
            continue
        dur = f"{int(r['duration'])}s" if r['duration'] else "—"
        lines.append(
            f"| {r['idx']} | @{r['uploader']} | {fmt_count(r['view_count'])} | "
            f"{fmt_count(r['like_count'])} | {fmt_count(r['comment_count'])} | {dur} | {r['note']} |"
        )
    lines.append("\n---\n")

    for r in results:
        lines.append(f"## Reel {r['idx']}")
        if r['note']:
            lines.append(f"**Category:** {r['note']}\n")
        lines.append(f"**Link:** [{r['url']}]({r['url']})\n")
        if "error" in r:
            lines.append(f"**Error:** {r['error']}\n")
            lines.append("\n---\n")
            continue
        lines.append(f"**Creator:** @{r['uploader']}  ")
        lines.append(f"**Duration:** {int(r['duration'])}s  ")
        lines.append(f"**Views:** {fmt_count(r['view_count'])}  ")
        lines.append(f"**Likes:** {fmt_count(r['like_count'])}  ")
        lines.append(f"**Comments:** {fmt_count(r['comment_count'])}  ")
        if r['upload_date']:
            d = r['upload_date']
            lines.append(f"**Posted:** {d[:4]}-{d[4:6]}-{d[6:8]}  ")
        lines.append("")
        if r['screenshot']:
            lines.append(f"**First-frame hook:**\n")
            lines.append(f"![hook]({SHOTS_DIR.name}/{r['screenshot']})\n")
        lines.append("**Transcript:**\n")
        lines.append(f"> {r['transcript'] or '_(no audio / silent reel)_'}\n")
        lines.append("\n---\n")

    REPORT.write_text("\n".join(lines))
    print(f"\n✅ Done. Report written to: {REPORT}")
    print(f"   Screenshots in: {SHOTS_DIR}")

    # Also dump raw json for future use
    (OUT_DIR / "data.json").write_text(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
