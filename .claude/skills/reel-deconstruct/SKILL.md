---
name: reel-deconstruct
description: Deconstruct a talking-head Instagram / TikTok / YouTube reel from a link — transcribe it, skeletonize the structure, name the framework, and break down the audience psychology (what the reel is DOING for the viewer). Use whenever Shekhar pastes a reel URL and asks to "break this down", "analyze this reel", "what's the framework here", "reverse-engineer this", "deconstruct this", or drops a link with a bit of context and wants the swipe-file teardown. ANALYSIS ONLY — it does not write or recreate scripts. Works on desktop (local transcriber CLI) and on cloud/web (hosted endpoint). Outputs a structured Markdown teardown.
allowed-tools: Read, Write, Edit, Bash
argument-hint: <reel-url> [+ optional context about what you want to learn from it]
---

You are deconstructing a **talking-head reel** for **Shekhar** — an organic Instagram growth strategist whose niche is **offline-strong, online-invisible founders** (people great at their craft/business in real life but invisible on social). His goal in studying a reel is almost never "summarize it" — it's **"reverse-engineer WHY this works so I can steal the structure, not the words."** Write every section to serve that goal.

The user's request: `$ARGUMENTS`

## Scope guardrail (read first)

This skill is **analysis only**. Do **not** write a recreated script, a new hook, or "here's your version." You may abstract the reel into a reusable *template* (fill-in-the-blank skeleton) and give a brief *transfer note* on how the framework maps to Shekhar's niche — but you stop at the structure. If the user explicitly asks you to *write/recreate* a reel afterward, that's a separate request you can then fulfill, but never volunteer it inside the teardown.

---

## Step 1 — Get the transcript

Parse `$ARGUMENTS`: the first `http(s)://` token is the **URL**; everything else is **optional context** (what Shekhar wants to learn, who the creator is, etc.). If there is no URL **and** no pasted transcript, ask once for a reel link and stop.

Get the transcript in this order of preference:

1. **If the user pasted a transcript** in their message, use it directly. Skip transcription.
2. **Desktop (local transcriber present):** if `/Users/shekhar/Claude Code/reel-transcriber/transcribe` exists, run:
   ```bash
   cd "/Users/shekhar/Claude Code/reel-transcriber" && ./transcribe "<URL>" --model small
   ```
   - Use a **300000ms** timeout. Filter out `[download]` progress and `Loading…`/`Transcribing…` stderr noise.
   - `--model small` is the default. Use `medium` only if the user asks for max accuracy; `tiny` for a quick/long-video check.
3. **Cloud / web (no local CLI):** POST to the hosted endpoint:
   ```bash
   curl -s -m 120 -X POST https://reel-transcriber-ii18.onrender.com/api/transcribe \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer $REEL_TRANSCRIBER_TOKEN" \
     -d '{"url":"<URL>"}'
   ```
   - The response is JSON: `{"id":…, "transcript":"…", "language":"…"}`. Use the `transcript` field.
   - The endpoint **requires the team token** in `REEL_TRANSCRIBER_TOKEN` (this is the `API_TOKEN` set on the Render dashboard). If the env var is unset or you get a 401/403, tell the user: *"Set `REEL_TRANSCRIBER_TOKEN` to the team token (Render → reel-transcriber → Environment → `API_TOKEN`), or just paste the transcript here and I'll analyze it."* Then stop.
   - Free-tier note: if the service was idle it may take ~50s to wake on the first call — that's normal, not a failure.

**Failure handling:** if transcription fails (private/restricted reel, network, >5-min video), report the error in one line and offer the fallback: *"Open the reel and paste the transcript here, or use the web UI at https://reel-transcriber-ii18.onrender.com."* Don't loop or retry silently more than once.

Also try to capture lightweight **metadata** if it's cheap to get (creator handle from the URL/context, view & like counts, on-screen hook text). On desktop you can read counts from yt-dlp; never block the teardown waiting on metadata — mark unknowns as `—`.

## Step 2 — Read the analysis frameworks

Before writing the teardown, read **`knowledge/analysis-frameworks.md`** (in this skill folder). It holds the binding taxonomies: the **beat sheet**, the **framework archetypes**, the **hook taxonomy**, the **psychology lenses**, and the **retention mechanics**. Use its exact vocabulary so every teardown is consistent and comparable across reels.

## Step 3 — Produce the teardown

Follow **`templates/report-template.md`** exactly — same section order, same headers. Fill every section. The eight layers:

1. **Verdict** — one sentence: what makes this reel work.
2. **At a glance** — creator, duration, counts, language, the literal hook line, the framework name.
3. **Skeleton (beat sheet)** — map the transcript to structural beats (Hook → Re-hook → Tension → Turn → Mechanism → Escalation → Payoff → CTA). For each beat: timestamp range (if known), the actual line, and its *function*. Not every reel has every beat — note which it skips, because the omission is itself a choice.
4. **Framework** — name it using an archetype from the knowledge file (or a clearly-named hybrid), and state the repeatable pattern in one line (the "formula").
5. **Hook anatomy** — classify the hook mechanism and explain in 1–2 sentences *why it stops the thumb*.
6. **Audience psychology** — the heart of the teardown. Who exactly is the target viewer; the belief/tension it pokes; the emotional before→after; the identity it flatters or the threat it neutralizes; the objection it preempts; why someone *saves or shares* it (social currency). This is the "what is this reel DOING for the audience" answer.
7. **Retention & delivery mechanics** — open loops, pacing, pattern interrupts, specificity, callbacks, list/escalation structure, and the one spot it would most likely lose people.
8. **Transferable template** — abstract the reel into a fill-in-the-blank skeleton Shekhar can reuse. Then a short **Transfer note** (2–4 bullets): does this framework map to offline-strong/online-invisible founders, and what would have to change. Keep it structural — no finished script.

## Hard rules

- **Steal the structure, not the words.** Every observation should help Shekhar reuse the *mechanism*. Avoid generic praise ("great hook!") — say *why* it works in terms of the taxonomy.
- **Quote the reel.** Anchor claims to actual lines from the transcript. Don't analyze a reel you couldn't transcribe — say so instead.
- **Name things.** Always give the framework and hook a concrete label from the taxonomy. A named pattern is a reusable pattern.
- **Honesty over flattery.** If a reel is mid, weak, or relies on the creator's existing audience rather than the structure, say that — it's more useful than inflating it.
- **No recreation.** Stop at the template + transfer note (see Scope guardrail).
- **Save nothing unless asked.** Output the teardown in chat. Only write a file if the user asks to save it.

## Notes

- If the user passes **multiple URLs**, deconstruct each one with its own full teardown, then add a short **"Patterns across all N"** section at the end (shared frameworks, recurring hook types).
- If the user gives context like *"I want to learn the hook"* or *"why does this get saves"*, weight that section heavier — but still fill the rest.
- This skill complements the existing `/transcribe` command (which only returns raw text). Use `/transcribe` when the user wants *just* the transcript; use this skill when they want the teardown.
