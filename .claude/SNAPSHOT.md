# thinking-narrator — Current Snapshot

**Last updated:** 2026-08-12
**Mode:** OVERWRITE — this file is always a snapshot of the current moment. Never append. Historical detail belongs in session summaries.

---

## Status

**Phase: v9 shipped 2026-08-12 — it reads the replies too.** The B012 "new scope" turned out to be: narrate the printed responses, not just the reasoning, with a switch between them; plus an app-style side-by-side layout. Both built and verified this sitting (see D10–D12).

v9 adds:
- **Read mode** — thoughts / replies / both (default **both**), a footer switch in the player and `--kinds` on both CLIs. One append-only block list per session tagged by kind, so the think→print interleaving survives and mode stays a client-side filter.
- **Separate voices per kind** (thought vs. reply) plus a sky/amber accent per kind, so which one is speaking is clear by ear and by eye.
- **Markdown→speech** for replies (`strip_markdown`): markers deleted, no word invented, code fences dropped. Verified 100% karaoke alignment on mixed prose+code replies.
- **App shell** — type `narrate` in any Windows Terminal window and THAT window is nested into a frame beside the narrator; close the frame and it is handed back plain. A toggle, not a mode (D13 + D14). Keeps real Windows Terminal (its tabs are how Arath switches sessions) rather than re-implementing a terminal. `launch-app.bat` remains the no-reparenting fallback (measured 1306×1040 + 614×1040 on 1920×1040).

Verified this sitting: 22/22 core fixture checks (kind extraction, the `user`-record guard, sidechain filter, markdown stripping, karaoke word-order invariant); all endpoints against a fixture root; live session read back correctly (49 blocks — 25 replies, 24 thoughts, interleaved); both window placements measured.

Prior work (v1→v8, one session 2026-07-26, session f9fcbe9b, 10 commits, ~1.7k lines):
- **Web player** (`server.py` + `index.html`) — the main entrance. Sessions sidebar with follow-active/lock and unread badges; per-chat thought log with karaoke word highlighting (edge-tts WordBoundary timestamps); custom transport (pause/seek/−10s/prev/next/volume/speed/8 neural voices); play-through mode with next-block prefetch; media keys; keyboard shortcuts; tab title/favicon state; jump-to-newest; MP3 cache with hourly eviction. Desktop shortcut "Thinking Narrator" launches it minimized; duplicate launch just opens the page.
- **CLI app** (`app.py`) — auto-follow the active chat with runtime lock/unlock/choose, history replay (all / last:N), neural voices with preview, space/s/q playback keys.
- **Ambient watcher** (`narrate.py`) — all chats at once, per-session SAPI voices; also holds the shared core (Tail, extract, clean, speak).

Verified: transcript flush timing (per message segment, ~one tool-cycle lag), block extraction, all 6 HTTP endpoints, word-timing monotonicity, per-key synth lock under concurrent requests, auto-follow switching, port-busy connect-probe.

**Blocked on:** Arath confirming the nested panes are usable in real work — typing/focus in the reparented terminal, tab switching, Alt+Tab, DPI, resize. Mechanics are verified programmatically (nest → `adopted=True`; close → window alive, `parent=0`, style restored byte-identical); *interaction* is not machine-checkable. One path is untested by execution on purpose: bare `narrate` uses `GetForegroundWindow`, and running it from a background context would have adopted Arath's live session — it was tested via explicit `-Hwnd` against a throwaway window instead.

**Shipped same evening (7/26):** blog post "I Made Claude Code Think Out Loud" live at arath.site/blog/i-made-claude-code-think-out-loud + project page at /work/thinking-narrator; repo flipped **PUBLIC** per D9. Both pages migrate into the unified Feed when the portfolio IA burst runs.

**Next immediate action:** Arath runs `launch-app.bat` and works a real sitting inside it — the v9 acid test. What to watch for is listed under Open questions; nothing else gets built until that log exists.

## Open questions

- **Is "both" the right default, or does reply+thought become too much talking?** The suspicion is that replies alone track the work and thoughts are the deep-dive mode. Untested by ear.
- Whether the two voices are distinguishable enough at speed, or whether replies want a spoken cue instead.
- Whether dropping code fences silently is right, or whether an audible marker is wanted despite the alignment cost (D11).
- Whether the 32% panel column is the right width in practice.
- Whether highlight drift is perceptible on long blocks at 2× (untested by ear, carried from v8).
