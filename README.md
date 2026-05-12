# Reel Transcriber

Paste an Instagram Reel link → get the full transcript. Built with FastAPI, yt-dlp, and OpenAI Whisper.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

Requires `ffmpeg` installed (`brew install ffmpeg` on Mac).

## Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/shekhar-stha/reel-transcriber)

One-click deploy via Render (free tier). The `render.yaml` and `Dockerfile` handle the rest.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WHISPER_MODEL` | `base` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large`) |
