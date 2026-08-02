"""Beckie-sales saved collection: OCR text hook + transcript + stats + talking-head flag.
Checkpoints after every reel. Gentle pacing.
"""
import json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
import whisper, yt_dlp

SD=Path("/Users/shekhar/Claude Code/reel-transcriber"); FF=SD/"bin"/"ffmpeg"; OCR=SD/"bin"/"ocr"
CK=Path("/Users/shekhar/Claude Code/reel-analysis/.ig_cookies.txt")
if FF.exists(): os.environ["PATH"]=f"{FF.parent}{os.pathsep}{os.environ.get('PATH','')}"
WORKLIST=Path("/Users/shekhar/Claude Code/reel-analysis/beckie_reels.txt")
CHECKPOINT=Path("/Users/shekhar/Claude Code/reel-analysis/beckie_progress.json")
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

def process(url, model):
    code=url.rstrip("/").split("/")[-1]
    rec={"url":url,"code":code}
    tmp=Path(tempfile.mkdtemp())
    try:
        opts={"format":"best[ext=mp4]/best","outtmpl":str(tmp/"v.%(ext)s"),"quiet":True,"no_warnings":True,"ffmpeg_location":str(FF.parent)}
        if CK.exists(): opts["cookiefile"]=str(CK)
        with yt_dlp.YoutubeDL(opts) as ydl: info=ydl.extract_info(url,download=True)
        video=next(p for p in tmp.iterdir() if p.suffix in (".mp4",".mkv",".webm",".mov"))
        rec["text_hook"]=text_hook(video,tmp)
        audio=tmp/"a.mp3"
        subprocess.run([str(FF),"-y","-i",str(video),"-vn","-acodec","libmp3lame","-q:a","4",str(audio)],check=True,capture_output=True,timeout=180)
        r=model.transcribe(str(audio),fp16=False)
        text=r["text"].strip(); dur=info.get("duration",0) or 0
        rec.update({"transcript":text,"language":r.get("language","?"),"uploader":info.get("uploader","") or "",
                    "duration":dur,"like_count":info.get("like_count"),"comment_count":info.get("comment_count"),
                    "talking_head": (len(text)/dur if dur else 0)>=6 and len(text)>=60 and dur>=15,
                    "status":"ok"})
    except Exception as e:
        rec.update({"status":"error","error":str(e)[:150]})
    finally: shutil.rmtree(tmp,ignore_errors=True)
    return rec

def main():
    urls=[l.strip() for l in WORKLIST.read_text().splitlines() if l.strip()]
    done={}
    if CHECKPOINT.exists():
        for r in json.loads(CHECKPOINT.read_text()): done[r["code"]]=r
    print(f"{len(urls)} reels, {len(done)} done. Loading Whisper small...")
    model=whisper.load_model("small")
    results=[]; ok=err=0
    for i,url in enumerate(urls,1):
        code=url.rstrip("/").split("/")[-1]
        if done.get(code,{}).get("status")=="ok":
            results.append(done[code]); ok+=1; print(f"[{i}/{len(urls)}] {code} cached"); continue
        print(f"[{i}/{len(urls)}] {code}")
        out=process(url,model); results.append(out)
        if out["status"]=="ok":
            ok+=1; th="TH" if out.get("talking_head") else "short"
            print(f"   ok {th} {int(out.get('duration',0))}s @{out.get('uploader','')}")
        else: err+=1; print(f"   ERR {out['error'][:50]}")
        merged={**done,**{r["code"]:r for r in results}}
        CHECKPOINT.write_text(json.dumps(list(merged.values()),indent=2,default=str))
        time.sleep(4)
    print(f"\nDone. {ok} ok, {err} err.")

if __name__=="__main__": main()
