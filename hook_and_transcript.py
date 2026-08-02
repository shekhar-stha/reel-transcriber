import os, sys, tempfile, shutil, subprocess
from pathlib import Path
import whisper, yt_dlp
SD=Path("/Users/shekhar/Claude Code/reel-transcriber"); FF=SD/"bin"/"ffmpeg"; OCR=SD/"bin"/"ocr"
CK=Path("/Users/shekhar/Claude Code/reel-analysis/.ig_cookies.txt")
if FF.exists(): os.environ["PATH"]=f"{FF.parent}{os.pathsep}{os.environ.get('PATH','')}"
FRAMES=["0.5","1.5","2.5","3.5"]
def ocr(p):
    try: return subprocess.run([str(OCR),str(p)],capture_output=True,text=True,timeout=30).stdout.strip()
    except: return ""
def text_hook(video,tmp):
    cands=[]
    for t in FRAMES:
        f=tmp/f"f{t}.jpg"
        try: subprocess.run([str(FF),"-y","-ss",t,"-i",str(video),"-frames:v","1","-q:v","3",str(f)],check=True,capture_output=True,timeout=30)
        except: continue
        if f.exists():
            txt=ocr(f)
            if txt: cands.append(txt)
    return max(cands,key=len) if cands else ""
model=whisper.load_model("small")
for url in sys.argv[1:]:
    tmp=Path(tempfile.mkdtemp())
    try:
        opts={"format":"best[ext=mp4]/best","outtmpl":str(tmp/"v.%(ext)s"),"quiet":True,"no_warnings":True,"ffmpeg_location":str(FF.parent)}
        if CK.exists(): opts["cookiefile"]=str(CK)
        with yt_dlp.YoutubeDL(opts) as ydl: info=ydl.extract_info(url,download=True)
        video=next(p for p in tmp.iterdir() if p.suffix in (".mp4",".mkv",".webm",".mov"))
        hook=text_hook(video,tmp)
        audio=tmp/"a.mp3"
        subprocess.run([str(FF),"-y","-i",str(video),"-vn","-acodec","libmp3lame","-q:a","4",str(audio)],check=True,capture_output=True,timeout=120)
        r=model.transcribe(str(audio),fp16=False)
        print(f"\n=====URL: {url}")
        print(f"CREATOR: @{info.get('uploader','?')} | {info.get('like_count','?')} likes")
        print(f"-----TEXT HOOK (on-screen)-----\n{hook}")
        print(f"-----TRANSCRIPT-----\n{r['text'].strip()}")
    except Exception as e:
        print(f"\n=====URL: {url}\n  FAILED: {str(e)[:120]}")
    finally: shutil.rmtree(tmp,ignore_errors=True)
