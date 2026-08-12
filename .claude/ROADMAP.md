# thinking-narrator — Roadmap

**Mode:** STABLE-ISH — overwrite whole phases when they complete or shift. Not a log of every change. See CONVENTIONS.md §5.4.

**Last updated:** 2026-07-26

---

## Phase 1: Prove the pipe (DONE 2026-07-26, v1–v2)

Transcript → speech. Measured flush timing, built the tail/extract core, SAPI narration, multi-chat watching with per-session voices.

## Phase 2: The app (DONE 2026-07-26, v3–v4)

Single-chat CLI app: session picker, history replay, edge-tts neural voices, auto-follow with runtime lock/unlock/choose.

## Phase 3: The player (DONE 2026-07-26, v5–v8)

Localhost web player: karaoke word tracking, custom dark transport UI, per-session cached views, loading states, comfort pack (media keys, play-through + prefetch, shortcuts, badges, cache cap, desktop launcher).

## Phase 4: Live with it (DONE — it produced Phase 4b)

The acid test never ran as written; using it produced a scope change instead, which is the same evidence by a shorter route. Arath's finding: reading the reasoning is only half of it — the printed replies are what track the work.

## Phase 4b: Read the replies (DONE 2026-08-12, v9)

Read mode (thoughts / replies / both) across all three entry points, per-kind voices and accents, markdown→speech for replies, and the side-by-side app layout (`launch-app.bat` + `?panel=1`). D10–D12.

## Phase 5: Live with v9 (CURRENT)

Arath works a real sitting inside `launch-app.bat`. The questions to answer are in SNAPSHOT "Open questions" — default mode, voice distinguishability, code-fence handling, panel width. Only fix what use proves broken.

## Phase 6: Candidates (unscheduled, gated on Phase 5 evidence)

- Embedded terminal in the page (ConPTY/pywinpty + xterm.js) — one window instead of two. Gated on D12: only if the two-window split proves to be the friction.

- ~~Blog post~~ DONE 2026-07-26 (shipped ahead of the acid test by Arath's call): "I Made Claude Code Think Out Loud" + /work page live; repo public.
- Per-session voice pinning in the web player.
- Offline neural TTS (piper) if edge-tts network dependency proves annoying.
- Highlight-drift calibration offset if ear-testing shows constant lead/lag.
- PWA install (icon in taskbar, no browser chrome) if daily use wants it.
