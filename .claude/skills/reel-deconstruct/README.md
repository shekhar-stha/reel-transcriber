# reel-deconstruct

Paste a talking-head reel link (Instagram / TikTok / YouTube) → get a structured **teardown**: transcript → skeleton → framework name → audience psychology → reusable template. **Analysis only — it does not write or recreate scripts.**

## How to use
Just drop a link, with or without context:

```
break this down: https://www.instagram.com/reel/XXXX/
what's the framework here? https://www.instagram.com/reel/XXXX/  (I care about the hook)
reverse-engineer these: <url1> <url2> <url3>
```

The skill auto-triggers on phrases like "break down / analyze / deconstruct / reverse-engineer this reel".

## Where the transcript comes from
1. **Pasted transcript** → used directly.
2. **Desktop** → local `reel-transcriber/transcribe` CLI (offline Whisper, no token).
3. **Cloud / web** → hosted endpoint `POST https://reel-transcriber-ii18.onrender.com/api/transcribe`, which needs the team token in the `REEL_TRANSCRIBER_TOKEN` env var (= the `API_TOKEN` set on Render). If it's not set, paste the transcript instead.

This is why the skill works on the cloud browser too: the transcription lives behind one hosted URL, and the analysis is pure Claude — no per-environment setup.

## Files
- `SKILL.md` — orchestration + rules
- `knowledge/analysis-frameworks.md` — the binding taxonomies (beat sheet, archetypes, hook types, psychology lenses, retention mechanics)
- `templates/report-template.md` — the exact output shape

## Related
- `/transcribe` — returns *just* the raw transcript, no analysis.
- Want recreation (write a new reel from the framework)? That's a separate step — ask after the teardown.
