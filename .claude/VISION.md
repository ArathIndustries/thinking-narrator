# thinking-narrator — Vision

**Mode:** STABLE — this file rarely changes. Overwrite only if the project's scope fundamentally shifts. See CONVENTIONS.md §5.3.

---

## One-line pitch

Hear Claude Code's extended thinking read aloud, near-live, while you work — and replay any session's thought history like an audiobook with word-level read-along.

## Why it exists

Claude Code writes every thinking block to the session transcript JSONL within seconds of generating it (measured 2026-07-26). That file was sitting there, machine-readable, with nobody listening. The narrator turns it into an ambient channel: keep working, or watch another screen, while the model's reasoning is spoken in a neural voice and word-highlighted on a player page. It answers "what is it doing right now?" without alt-tabbing and "what was it thinking an hour ago?" without scrolling.

Born 2026-07-26 from a curiosity question ("does the thinking text take up context? where is it saved?") that became a v1→v8 build the same day.

## Who it serves

Arath, on the desktop, running one or more Claude Code chats. Single-user, localhost-only by design.

## Non-goals

- Not a cloud service, not multi-user; never binds beyond 127.0.0.1.
- Not a transcript editor or analytics tool — it reads, never writes to transcripts.
- No paid TTS APIs; edge-tts (free, keyless, network) + Windows SAPI offline fallback only.
