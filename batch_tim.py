"""Transcribe timbiohacker top-30 reels. Stats come from the CSV (tim_top30.json).
Checkpoints after each. Gentle pacing."""
import json, os, shutil, subprocess, tempfile, time
from pathlib import Path
import whisper, yt_dlp

SD=Path("/Users/shekhar/Claude Code/reel-transcriber"); FF=SD/"bin"/"ffmpeg"
CK=Path("/Users/shekhar/Claude Code/reel-analysis/.ig_cookies.txt")
if FF.exists(): os.environ["PATH"]=f"{FF.parent}{os.pathsep}{os.environ.get('PATH','')}"
WORK=Path("/Users/shekhar/Claude Code/reel-analysis/tim_top30.json")
CP=Path("/Users/shekhar/Claude Code/reel-analysis/tim_progress.json")

def transcribe(url, model):
    tmp=Path(tempfile.mkdtemp())
    try:
        opts={"format":"bestaudio/best","outtmpl":str(tmp/"a.%(ext)s"),"postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"128"}],"quiet":True,"no_warnings":True,"ffmpeg_location":str(FF.parent)}
        if CK.exists(): opts["cookiefile"]=str(CK)
        with yt_dlp.YoutubeDL(opts) as ydl: info=ydl.extract_info(url,download=True)
        audio=next(p for p in tmp.iterdir() if p.suffix in (".mp3",".m4a",".wav"))
        r=model.transcribe(str(audio),fp16=False)
        return {"transcript":r["text"].strip(),"duration":info.get("duration",0) or 0,"status":"ok"}
    except Exception as e:
        return {"status":"error","error":str(e)[:150]}
    finally: shutil.rmtree(tmp,ignore_errors=True)

def main():
    work=json.loads(WORK.read_text())
    done={}
    if CP.exists():
        for r in json.loads(CP.read_text()): done[r["code"]]=r
    print(f"{len(work)} reels; {len(done)} done. Loading Whisper small...")
    model=whisper.load_model("small")
    results=[]; ok=err=0
    for i,item in enumerate(work,1):
        code=item["code"]
        if done.get(code,{}).get("status")=="ok":
            results.append(done[code]); ok+=1; print(f"[{i}/{len(work)}] {code} cached"); continue
        print(f"[{i}/{len(work)}] {code} ({item['views']:,} views)")
        out=transcribe(item["url"],model)
        rec={**item,**out}
        results.append(rec)
        if out["status"]=="ok": ok+=1; print(f"   ok {len(out['transcript'])}c")
        else: err+=1; print(f"   ERR {out['error'][:50]}")
        merged={**done,**{r["code"]:r for r in results}}
        CP.write_text(json.dumps(list(merged.values()),indent=2,default=str))
        time.sleep(4)
    print(f"\nDone. {ok} ok, {err} err.")

if __name__=="__main__": main()
