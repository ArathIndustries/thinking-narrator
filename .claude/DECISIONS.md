# thinking-narrator — Decisions Log

**Mode:** APPEND-ONLY. Never overwrite a past decision. If a decision is reversed, append a new entry referencing the original. See CONVENTIONS.md §5.5.

---

## 2026-07-26 — D1: Read the transcript JSONL; never hook or wrap the CLI

Claude Code appends each assistant message segment (thinking included) to `~\.claude\projects\<slug>\<session>.jsonl` roughly when the segment's tool calls begin executing — measured in-session by checking the file mid-turn. Tailing that file is read-only, zero-risk to the chat, and survives Claude Code updates better than any hook. Lag is one tool-execution cycle (seconds); accepted.

## 2026-07-26 — D2: The browser is the player

Pause, scrub/rewind, volume, and speed were requested; a terminal delivers all of them badly. A localhost web page gets native audio transport, and Python keeps the parts it is good at (tailing, synthesis, caching). Stdlib `http.server` only; no framework.

## 2026-07-26 — D3: edge-tts for voices, SAPI as fallback, no paid APIs

Windows 10 ships two robotic SAPI voices. edge-tts provides 47 English neural voices, free, keyless (network required); WordBoundary events also give word timestamps, which became the karaoke feature. On synthesis failure the CLI falls back to SAPI with a printed warning; the web player reports and stops.

## 2026-07-26 — D4: No truncation, ever (Arath ruling, mid-build)

Original default cut blocks at 1500 chars. Arath: "what is the point of stopping the thoughts if that is literally what I want this to do." `--max-chars` became opt-in (default 0); the skip control replaces truncation as the escape hatch.

## 2026-07-26 — D5: Follow-active by default, lock as the user's choice

The narrator follows whichever chat is generating (newest thinking block wins) and switches with announcements; locking to one chat is a single action (sidebar click / `l` key / `--session`). Matches how Arath actually works — several chats, one attention stream.

## 2026-07-26 — D6: Word-highlight alignment skips TTS-normalized tokens

Boundary words are matched to the original text with a forward `indexOf` cursor; tokens the voice normalizes (digits read as words, symbols) simply don't get a span, and the highlight steps over them. Chosen over trying to reproduce the normalizer — simple, degrades gracefully, correctness of the rest untouched.

## 2026-07-26 — D7: Localhost-only bind; private GitHub repo first

Server binds 127.0.0.1 exclusively. Repo pushed private under ArathIndustries; flipping public is an explicit Arath ruling gated on the blog decision (content audited clean — no secrets, local paths only).

## 2026-07-26 — D8: CPI five-question checklist (per design/continuous-improvement.md)

1. **DETECT emission:** session summaries tagged `thinking-narrator` via /handoff → TIMELINE; spoke INDEX.md bookmarks.
2. **Standard started from:** canonical-homes (code → Automation_Station + git), WAT discipline (deterministic tail/synth/cache; fail-loud asserts; probabilistic reasoning only at design time), hub spoke template. Web project-seeds templates were NOT used — this is a localhost stdlib tool, not a deployed site.
3. **Verification evidence:** commit messages carry verified-by-execution notes; LESSONS.md troubleshooting table records symptom→cause→fix→verification for every defect found.
4. **Heartbeat/fail-loud:** user-launched (not scheduled), so no heartbeat; fail-loud = server asserts surface as HTTP 500s shown in the player status line, CLI asserts stop with messages, cache prune and count warmer print warnings on error rather than dying silently.
5. **Acid test:** BACKLOG task due 2026-08-02 — one week of real use, friction logged; ROADMAP Phase 5 is gated on it.
