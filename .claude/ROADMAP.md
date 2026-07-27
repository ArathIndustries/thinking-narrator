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

## Phase 4: Live with it (CURRENT)

Daily use. Acid test due 2026-08-02: a week of real listening, friction logged to BACKLOG. Only fix what use proves broken.

## Phase 5: Candidates (unscheduled, gated on Phase 4 evidence)

- Blog post on the Arath Industries blog (LESSONS.md is the raw material; repo flip to public is Arath's ruling).
- Per-session voice pinning in the web player.
- Offline neural TTS (piper) if edge-tts network dependency proves annoying.
- Highlight-drift calibration offset if ear-testing shows constant lead/lag.
- PWA install (icon in taskbar, no browser chrome) if daily use wants it.
