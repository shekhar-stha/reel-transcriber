import os, sys, tempfile, shutil
from pathlib import Path
import whisper, yt_dlp
SD = Path("/Users/shekhar/Claude Code/reel-transcriber"); FF = SD/"bin"/"ffmpeg"
CK = Path("/Users/shekhar/Claude Code/reel-analysis/.ig_cookies.txt")
if FF.exists(): os.environ["PATH"]=f"{FF.parent}{os.pathsep}{os.environ.get('PATH','')}"
model=whisper.load_model("medium")
for url in sys.argv[1:]:
    tmp=Path(tempfile.mkdtemp())
    try:
        opts={"format":"bestaudio/best","outtmpl":str(tmp/"a.%(ext)s"),
              "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"128"}],
              "quiet":True,"no_warnings":True,"ffmpeg_location":str(FF.parent)}
        if CK.exists(): opts["cookiefile"]=str(CK)
        with yt_dlp.YoutubeDL(opts) as ydl: info=ydl.extract_info(url,download=True)
        audio=next(p for p in tmp.iterdir() if p.suffix in (".mp3",".m4a",".wav"))
        r=model.transcribe(str(audio),fp16=False)
        print(f"\n=====URL: {url}")
        print(f"CREATOR: @{info.get('uploader','?')} | {info.get('like_count','?')} likes | {int(info.get('duration',0))}s")
        print("-----PURE TRANSCRIPT-----")
        print(r["text"].strip())
    except Exception as e:
        print(f"\n=====URL: {url}\n  FAILED: {str(e)[:120]}")
    finally: shutil.rmtree(tmp,ignore_errors=True)
