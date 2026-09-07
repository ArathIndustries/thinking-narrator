# thinking-narrator — Current Snapshot

**Last updated:** 2026-09-07
**Mode:** OVERWRITE — this file is always a snapshot of the current moment. Never append. Historical detail belongs in session summaries.

---

## Status

**Phase: v11 built 2026-09-07 — Talk mode, the voice loop (D16).** Claude Code `/voice` in (hold Space; Windows default capture = Corsair headset mic, verified), narrator out. The narrator gained a **Talk** preset: Replies only, one-deep queue (newest wins — `narrate.py`'s drop-backlog ported to the player), play-through ignored, kinds restored on exit. Footer toggle, persisted; `?talk=1` / `narrate -Talk` forces it. Paired with the `speech-mode` skill (hub `skills/speech-mode/`, body `feedback/feedback_speech_mode_replies.md`): spoken replies are short prose, no lists / paths / code / tables.

Verified this sitting: player script `node --check` clean; live server already serving the new build (the open pane reloads at its next pause); skill registered in the running session. **Not yet verified by ear** — the toggle, the drain under real replies, and whether the loop feels like a conversation.

**Next immediate action (B110, the acid test):** Arath runs `narrate -Talk` (or ticks Talk in the footer of the pane already open), holds Space, and works a 20-minute study sitting on Capstone Quiz 2 material with the keyboard untouched except Space. Writes the verdict on the questions below into this file. Suggested but not applied (harness edits are Arath's): `"voice": {"autoSubmit": true}` in `~/.claude/settings.json` so a release sends without Enter.

Prior phases (v1→v10.1): web player + karaoke, CLI app, ambient watcher, three kinds with voices per kind, tool-call summaries, markdown→speech, app shell that nests the live terminal via SetParent (D13–D15), v10.1 fixes (local timestamps, looping playback, latched auto-reload). Detail: DECISIONS.md and the session summaries in INDEX.md.

## Open questions

- **Does Talk feel like a conversation?** Lag is about one tool cycle plus synthesis; is that acceptable when waiting for an answer, or does it want a spoken "thinking" cue?
- **Does newest-wins drop anything you wanted?** A reply that precedes a tool run is dropped if a later reply arrives before it plays. The speech-mode skill asks for silent tool runs so this stays rare; measure it.
- **Which kinds belong in the default for the non-Talk player?** Measured: 198 tool calls to 54 thoughts and 59 replies. Talk answers this for the loop; the reading-along case is still open.
- Whether the reply voice (Aria) is right for a study partner, or a calmer one reads better over 20 minutes.
- Whether dropping code fences silently is right (D11) — in Talk the skill avoids code, so this matters only outside Talk.
- Whether the 32% panel column is the right width; whether highlight drift is perceptible at 2× (carried).
