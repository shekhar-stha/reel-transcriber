# Reel Transcriber

Paste an Instagram Reel (or YouTube, TikTok, etc.) link → get the full transcript. Runs 100% offline on your laptop using OpenAI Whisper.

## Quick start (you, on this Mac)

Everything is already installed. From this directory, just run:

```bash
./transcribe "https://www.instagram.com/reel/XXXXXXX/"
```

First run downloads the Whisper model (~150 MB for `base`). After that it's fully offline.

### Options

```bash
# Save to file
./transcribe "https://..." --out transcript.txt

# Use a different model (tiny/base/small/medium/large)
./transcribe "https://..." --model small
```

| Model  | Size    | Speed     | Accuracy |
|--------|---------|-----------|----------|
| tiny   | 75 MB   | Fastest   | OK       |
| base   | 150 MB  | Fast      | Good     |
| small  | 500 MB  | Medium    | Better   |
| medium | 1.5 GB  | Slow      | Great    |
| large  | 3 GB    | Slowest   | Best     |

## Setup on another machine (for teammates)

```bash
# 1. Clone
git clone https://github.com/shekhar-stha/reel-transcriber
cd reel-transcriber

# 2. Install uv (manages Python, no admin needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install deps
uv sync

# 4. Get ffmpeg (Mac)
curl -L -o /tmp/ffmpeg.zip https://evermeet.cx/ffmpeg/ffmpeg-7.1.zip
unzip /tmp/ffmpeg.zip -d bin/
chmod +x bin/ffmpeg

# 5. Run
./transcribe "https://www.instagram.com/reel/XXXXXXX/"
```

On Linux/Windows, install ffmpeg via your package manager (`apt install ffmpeg` or download from ffmpeg.org).
