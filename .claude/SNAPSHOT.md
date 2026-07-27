# thinking-narrator — Current Snapshot

**Last updated:** 2026-07-26
**Mode:** OVERWRITE — this file is always a snapshot of the current moment. Never append. Historical detail belongs in session summaries.

---

## Status

**Phase: v8 shipped, in daily-use trial.** Built v1→v8 in one session (2026-07-26, session f9fcbe9b), 10 commits, ~1.7k lines, all entry points verified by execution against synthetic fixtures.

What exists:
- **Web player** (`server.py` + `index.html`) — the main entrance. Sessions sidebar with follow-active/lock and unread badges; per-chat thought log with karaoke word highlighting (edge-tts WordBoundary timestamps); custom transport (pause/seek/−10s/prev/next/volume/speed/8 neural voices); play-through mode with next-block prefetch; media keys; keyboard shortcuts; tab title/favicon state; jump-to-newest; MP3 cache with hourly eviction. Desktop shortcut "Thinking Narrator" launches it minimized; duplicate launch just opens the page.
- **CLI app** (`app.py`) — auto-follow the active chat with runtime lock/unlock/choose, history replay (all / last:N), neural voices with preview, space/s/q playback keys.
- **Ambient watcher** (`narrate.py`) — all chats at once, per-session SAPI voices; also holds the shared core (Tail, extract, clean, speak).

Verified: transcript flush timing (per message segment, ~one tool-cycle lag), block extraction, all 6 HTTP endpoints, word-timing monotonicity, per-key synth lock under concurrent requests, auto-follow switching, port-busy connect-probe.

**Blocked on:** nothing.

**Next immediate action:** Arath uses it for a real work week; acid-test friction log due 2026-08-02 (BACKLOG task). Arath rules on flipping the GitHub repo public ahead of the blog post.

## Open questions

- Public repo timing (currently private; content is clean of secrets — paths only).
- Whether highlight drift is perceptible on long blocks at 2× (untested by ear).
