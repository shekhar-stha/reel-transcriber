#!/usr/bin/env python3
"""Batch transcribe Instagram links from a CSV and create CSV/PDF outputs."""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import tempfile
import time
import uuid
from pathlib import Path

import whisper
import yt_dlp
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SCRIPT_DIR = Path(__file__).parent.resolve()
FFMPEG_PATH = SCRIPT_DIR / "bin" / "ffmpeg"
DEFAULT_OUT_DIR = SCRIPT_DIR / "outputs"

if FFMPEG_PATH.exists():
    os.environ["PATH"] = f"{FFMPEG_PATH.parent}{os.pathsep}{os.environ.get('PATH', '')}"


def load_checkpoint(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    items = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            url = item.get("POST URL") or item.get("url")
            if url:
                items[url] = item
    return items


def append_checkpoint(path: Path, item: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
        f.flush()


def clean_url(url: str) -> str:
    return (url or "").strip().split("#", 1)[0].rstrip("/")


def download_audio(url: str, tmp_dir: str, max_duration: int) -> tuple[str | None, dict]:
    output_template = os.path.join(tmp_dir, f"{uuid.uuid4().hex}.%(ext)s")
    common = {
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": str(FFMPEG_PATH.parent) if FFMPEG_PATH.exists() else None,
    }
    with yt_dlp.YoutubeDL({**common, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)

    duration = int(info.get("duration") or 0)
    if duration and duration > max_duration:
        return None, {"duration": duration, "skip_reason": f"too long ({duration}s)"}

    ydl_opts = {
        **common,
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    for f in Path(tmp_dir).iterdir():
        if f.suffix.lower() in (".mp3", ".m4a", ".wav", ".webm", ".opus"):
            return str(f), {"duration": duration, "skip_reason": ""}
    raise RuntimeError("No audio file found after download")


def looks_like_speech(result: dict) -> tuple[bool, str]:
    text = (result.get("text") or "").strip()
    if not text:
        return False, "empty transcript"

    normalized = re.sub(r"\s+", " ", text).strip().lower()
    filler = {
        "thank you",
        "thanks for watching",
        "you",
        "music",
        "[music]",
        "(music)",
    }
    if normalized in filler:
        return False, "likely silence/music hallucination"

    words = re.findall(r"[A-Za-z][A-Za-z']+", text)
    if len(words) < 4:
        segments = result.get("segments") or []
        avg_no_speech = (
            sum(float(s.get("no_speech_prob", 0)) for s in segments) / len(segments)
            if segments else 1
        )
        if avg_no_speech > 0.35:
            return False, "too little speech"

    return True, ""


def transcribe_url(model, url: str, max_duration: int) -> dict:
    tmp_dir = tempfile.mkdtemp()
    try:
        audio_path, meta = download_audio(url, tmp_dir, max_duration)
        if not audio_path:
            return {
                "transcript": "",
                "language": "",
                "duration_seconds": meta.get("duration", ""),
                "status": "skipped",
                "skip_reason": meta.get("skip_reason", "skipped"),
            }

        result = model.transcribe(audio_path, fp16=False)
        is_speech, reason = looks_like_speech(result)
        transcript = (result.get("text") or "").strip() if is_speech else ""
        return {
            "transcript": transcript,
            "language": result.get("language", ""),
            "duration_seconds": meta.get("duration", ""),
            "status": "transcribed" if is_speech else "skipped",
            "skip_reason": "" if is_speech else reason,
        }
    finally:
        for f in Path(tmp_dir).iterdir():
            f.unlink(missing_ok=True)
        os.rmdir(tmp_dir)


def write_csv(rows: list[dict], output_path: Path):
    fieldnames = list(rows[0].keys()) if rows else []
    for field in ["TRANSCRIPT", "TRANSCRIPT_LANGUAGE", "DURATION_SECONDS", "TRANSCRIPT_STATUS", "SKIP_REASON"]:
        if field not in fieldnames:
            fieldnames.append(field)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def para(text: str, style):
    return Paragraph(html.escape(str(text or "")).replace("\n", "<br/>"), style)


def write_pdf(rows: list[dict], output_path: Path):
    transcribed = [r for r in rows if r.get("TRANSCRIPT")]
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title="Instagram Reel Transcript Report",
    )
    styles = getSampleStyleSheet()
    title = styles["Title"]
    h2 = styles["Heading2"]
    body = ParagraphStyle("Body", parent=styles["BodyText"], leading=13, fontSize=9)
    small = ParagraphStyle("Small", parent=styles["BodyText"], leading=11, fontSize=8, textColor=colors.HexColor("#444444"))

    story = [
        Paragraph("Instagram Reel Transcript Report", title),
        Spacer(1, 0.12 * inch),
        Paragraph(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", small),
        Paragraph(f"Rows in source CSV: {len(rows)}", small),
        Paragraph(f"Reels with detected spoken transcript: {len(transcribed)}", small),
        Spacer(1, 0.2 * inch),
    ]

    for idx, row in enumerate(transcribed, start=1):
        story.append(Paragraph(f"{idx}. @{row.get('USERNAME', '')}", h2))
        metrics = [
            ["Link", para(row.get("POST URL", ""), small)],
            ["Posted", para(row.get("POST AT", ""), small)],
            ["Views", para(row.get("VIEWS", ""), small)],
            ["Likes", para(row.get("LIKES", ""), small)],
            ["Comments", para(row.get("COMMENTS", ""), small)],
            ["Reposts", para(row.get("REPOST", ""), small)],
            ["Duration", para(row.get("DURATION_SECONDS", ""), small)],
            ["Language", para(row.get("TRANSCRIPT_LANGUAGE", ""), small)],
        ]
        table = Table(metrics, colWidths=[0.85 * inch, 6.0 * inch])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#666666")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
        if row.get("POST CAPTION"):
            story.append(Spacer(1, 0.08 * inch))
            story.append(Paragraph("Caption", styles["Heading4"]))
            story.append(para(row.get("POST CAPTION", ""), small))
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph("Transcript", styles["Heading4"]))
        story.append(para(row.get("TRANSCRIPT", ""), body))
        if idx != len(transcribed):
            story.append(PageBreak())

    doc.build(story)


def main():
    parser = argparse.ArgumentParser(description="Batch transcribe Instagram CSV rows and create a PDF report.")
    parser.add_argument("csv_path")
    parser.add_argument("--model", default="base", choices=["tiny", "base", "small", "medium", "large"])
    parser.add_argument("--max-duration", type=int, default=300)
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N rows, for testing.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    csv_path = Path(args.csv_path).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = csv_path.stem.replace(" ", "_").replace("(", "").replace(")", "")
    checkpoint_path = out_dir / f"{stem}_checkpoint.jsonl"
    output_csv = out_dir / f"{stem}_with_transcripts.csv"
    output_pdf = out_dir / f"{stem}_transcripts.pdf"

    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[:args.limit]

    completed = load_checkpoint(checkpoint_path)
    print(f"Loaded {len(rows)} rows. Checkpoint has {len(completed)} completed URLs.", flush=True)
    print(f"Loading Whisper model: {args.model}", flush=True)
    model = whisper.load_model(args.model)

    enriched = []
    for idx, row in enumerate(rows, start=1):
        row = dict(row)
        url = clean_url(row.get("POST URL", ""))
        row["POST URL"] = url
        if not url:
            result = {"transcript": "", "language": "", "duration_seconds": "", "status": "skipped", "skip_reason": "missing url"}
        elif url in completed:
            c = completed[url]
            result = {
                "transcript": c.get("TRANSCRIPT", ""),
                "language": c.get("TRANSCRIPT_LANGUAGE", ""),
                "duration_seconds": c.get("DURATION_SECONDS", ""),
                "status": c.get("TRANSCRIPT_STATUS", ""),
                "skip_reason": c.get("SKIP_REASON", ""),
            }
            print(f"[{idx}/{len(rows)}] cached {url} -> {result['status']}", flush=True)
        else:
            print(f"[{idx}/{len(rows)}] processing {url}", flush=True)
            try:
                result = transcribe_url(model, url, args.max_duration)
            except Exception as e:
                message = str(e)
                no_audio_markers = (
                    "unable to obtain file audio codec",
                    "does not contain any stream",
                    "No audio file found",
                )
                if any(marker in message for marker in no_audio_markers):
                    result = {
                        "transcript": "",
                        "language": "",
                        "duration_seconds": "",
                        "status": "skipped",
                        "skip_reason": "no audio stream",
                    }
                else:
                    result = {
                        "transcript": "",
                        "language": "",
                        "duration_seconds": "",
                        "status": "error",
                        "skip_reason": message,
                    }
            print(f"[{idx}/{len(rows)}] {result['status']}: {result.get('skip_reason') or 'ok'}", flush=True)

        row["TRANSCRIPT"] = result.get("transcript", "")
        row["TRANSCRIPT_LANGUAGE"] = result.get("language", "")
        row["DURATION_SECONDS"] = result.get("duration_seconds", "")
        row["TRANSCRIPT_STATUS"] = result.get("status", "")
        row["SKIP_REASON"] = result.get("skip_reason", "")
        enriched.append(row)
        if url and url not in completed:
            append_checkpoint(checkpoint_path, row)
            completed[url] = row
        write_csv(enriched + [
            {**r, **{
                "TRANSCRIPT": completed.get(clean_url(r.get("POST URL", "")), {}).get("TRANSCRIPT", ""),
                "TRANSCRIPT_LANGUAGE": completed.get(clean_url(r.get("POST URL", "")), {}).get("TRANSCRIPT_LANGUAGE", ""),
                "DURATION_SECONDS": completed.get(clean_url(r.get("POST URL", "")), {}).get("DURATION_SECONDS", ""),
                "TRANSCRIPT_STATUS": completed.get(clean_url(r.get("POST URL", "")), {}).get("TRANSCRIPT_STATUS", ""),
                "SKIP_REASON": completed.get(clean_url(r.get("POST URL", "")), {}).get("SKIP_REASON", ""),
            }}
            for r in rows[idx:]
        ], output_csv)

    write_csv(enriched, output_csv)
    write_pdf(enriched, output_pdf)
    print(f"Done. CSV: {output_csv}", flush=True)
    print(f"Done. PDF: {output_pdf}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted. Progress is saved in the checkpoint file.", file=sys.stderr)
        raise
