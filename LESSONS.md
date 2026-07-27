# thinking-narrator — Build Log & Lessons

Raw material for the Arath Industries blog post. One session, 2026-07-26,
v1 → v8, 10 commits, ~1,700 lines. Every claim below was verified by
execution during the build; nothing here is recalled from documentation.

## The origin

The project started as a side question in an unrelated session: *"does the
thinking text I can expand in the CLI take up context? where is it coming
from / being printed to / saved?"* Answering it revealed that Claude Code
writes every thinking block to a session transcript (JSONL) on disk — and a
follow-up grep mid-conversation proved the file updates while the turn is
still running. From "the data is right there, live" to a working narrator
was about an hour; the rest of the day was making it *good*.

## Timeline (all one day)

| ver | what shipped |
|---|---|
| v1 | Tail newest transcript → Windows SAPI speech. Measured flush timing first, built second. |
| v2 | Multi-chat: tail every session, per-session voices (David/Zira), spoken "Session N" prefix. |
| v3 | CLI app: session picker, history replay (all/last:N), edge-tts neural voices, playback keys. No-truncation ruling. |
| v4 | Auto-follow the active chat; runtime lock/unlock/choose. Line-buffering fix. |
| v5 | Localhost web player: session sidebar, clickable thought cards, native audio transport, MP3+cache. |
| v6 | Karaoke word highlighting from WordBoundary timestamps; darker/wider UI; custom transport bar. |
| v7 | Scroll-to-newest with bottom-pinning; "synthesizing…" states; double-click + server race guards; per-session cached views; "thinking…" indicator. |
| v8 | Comfort pack: media keys, play-through + prefetch, keyboard shortcuts, unread badges, tab state, jump-to-newest, cache cap, desktop launcher. |

## Measured facts worth publishing

- **Transcript flush timing:** Claude Code appends each assistant message
  segment to the JSONL roughly when that segment's tool calls begin
  executing — narration lags generation by one tool-execution cycle
  (seconds), not by turns. Proven by counting thinking blocks on disk from
  *inside* a running turn: a block generated minutes earlier was present;
  the one generated immediately before the check was not yet.
- **Thinking blocks are not uniform:** the same transcript held raw
  thinking (9,848 chars) and model-produced summaries (184 chars). The file
  stores exactly what the CLI shows.
- **Thinking context behavior:** within a turn, thinking blocks ride along
  in every follow-up API request; across turns they're stripped. The
  transcript on disk is the only place they persist.

## Troubleshooting loops (symptom → cause → fix → proof)

1. **SAPI test spoke garbage errors** → the test command went through Git
   Bash, which ate `$s` variables before PowerShell saw them → run PS via
   the PowerShell tool or Python subprocess list-args → re-run spoke.
2. **Background test captured zero output** → Python block-buffers stdout
   when redirected; force-kill discarded the buffer → `line_buffering=True`
   on both streams (also makes real-use log redirection work) → capture
   showed the full follow/switch sequence.
3. **Word timings came back empty** → edge-tts 7.2.8 defaults to
   `SentenceBoundary`; the docs-remembered behavior (word events by
   default) was wrong for this version → pass `boundary="WordBoundary"`,
   bump the cache key so stale empty sidecars die → fixture returned 5
   words, monotonic timestamps.
4. **"Port already in use" detection never fired** → `http.server` sets
   `SO_REUSEADDR`, and on Windows that lets a second server bind a live
   port with no error — the duplicate silently *served* → probe the port
   with `connect_ex` before binding; also `allow_reuse_address = False` →
   duplicate now exits 0 with a message, original unaffected.
5. **Rapid clicks on a long thought stacked concurrent synthesis** → no
   client dedupe, and two server threads could write the same cache file →
   client: pending-key ignore + newer-click-supersedes token; server:
   per-key `threading.Lock` → two simultaneous uncached requests returned
   byte-identical MP3s.
6. **Hand-written test fixture had malformed JSON** (stray `]`) → would
   have tested the parse-warning path instead of the sidechain filter →
   caught on re-read before running; fixed → filter test meaningful.

## Design lessons

- **Measure before building.** The whole project rests on flush timing that
  was verified empirically in ten minutes. The v1 README recorded those
  measurements; every later feature (near-live badge counts, the
  "thinking…" indicator) leaned on them.
- **Choose the medium by the controls it gives you free.** Pause, scrub,
  volume, speed — a week of TUI work, or one `<audio>` element. Moving to
  the browser made an entire feature-request list disappear.
- **The best data is the data already there.** Word-level karaoke sounded
  like a hard feature; edge-tts was already emitting per-word timestamps —
  the feature was one parameter plus an alignment loop. Look for what the
  pipeline already produces before engineering anything.
- **Users name defaults wrong; rulings fix them.** Truncating thoughts at
  1500 chars seemed sensible ("75 s of speech") and was flatly wrong for
  the actual purpose ("that is literally what I want this to do").
  Recorded as D4; skip-key replaced truncation.
- **Windows details bite exactly twice** — once when you hit them, once
  when you forget them. Hence the gotchas list in `.claude/ROUTING.md`
  (SO_REUSEADDR, bash-vs-PS quoting, buffer loss, cache versioning).

## Numbers for the post

- 1 session, 10 commits, 3 entry points, ~1,700 tracked lines.
- 6 HTTP endpoints; 47 neural voices reachable, 8 curated.
- Server deps: Python stdlib + one package (edge-tts). Frontend deps: none.
- 6 defects found by testing during the build, all fixed and re-verified
  in-session; 0 known open defects at v8.

## Blog angles (pick one, don't do all)

1. "I made Claude Code think out loud" — the demo-first story, ends with
   the karaoke player following the model's reasoning in real time.
2. "Your tools are already publishing data — listen to it" — the
   transcript-as-API angle; measure, tail, transform.
3. "From CLI to creature comforts in one day" — the v1→v8 evolution as a
   case study in letting user friction order the roadmap (every version
   answered a real complaint from use, not a spec).
