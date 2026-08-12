# thinking-narrator

Speaks Claude Code aloud, near-live or as history replay — both the
`thinking` blocks and the printed replies, either alone or interleaved.

**Read mode** (v9) is three independent toggles — **Thoughts** (reasoning),
**Replies** (what was printed to the terminal), **Tools** (what it is doing:
"Editing index.html", "Running: commit and push", "Searching for
extract_blocks in narrate.py"). Any combination works, including one alone;
turning the last one off is refused. Footer of the web player, `--kinds` on
both CLIs. Each kind gets its own voice and its own accent colour, so what is
speaking is clear without reading the screen.

Calibration, measured on one real session: **198 tool calls to 54 thoughts
and 59 replies.** Tool calls are roughly two thirds of everything, so leaving
Tools on means most of what you hear is tool narration — and because speech is
slower than generation, the queue falls behind faster with them on. That is
the reason they are a separate toggle rather than folded into the others.

Printed replies are markdown, so they are stripped to speakable prose before
synthesis: headings, list markers, emphasis, links, and table pipes go; code
fences are dropped (a reply that is *only* code speaks "Code block."). The
rule is that markers are deleted but no word is ever invented — that is what
keeps the karaoke highlighting aligned against the raw text on the card.

Three entry points:

- **`server.py`** — the web player (recommended). `py server.py` opens
  http://127.0.0.1:8917 — session sidebar, scrollable thought log, and a
  real audio player. This is where the intuitive controls live:

  | want | how |
  |---|---|
  | pick any mix of thoughts / replies / tools | the three toggles in the footer |
  | tell them apart by ear | a voice dropdown per kind |
  | pause / resume mid-thought | player pause button |
  | rewind / scrub inside a thought | drag the seek bar (Range-request backed) |
  | replay any past thought | click its card in the log |
  | volume | player volume slider |
  | change voice | voice dropdown (applies to the next thought) |
  | speed | speed dropdown (instant, browser playbackRate) |
  | follow the chat I'm in | "Follow active chat" toggle (auto-switches) |
  | lock to one chat | click it in the sidebar (turns follow off) |
  | stop auto-reading, browse quietly | untick "Read new thoughts" |

  MP3s are synthesized per block (edge-tts) and cached in
  `%TEMP%\thinking-narrator-cache`, so replays are instant. History loads
  silently; only newly arriving thoughts auto-play. Amber lamp = playing;
  the playing card's left rail fills with progress. Localhost-only bind.

  **App shell (v9) — one window, and it is a toggle:** type `narrate` in any
  Windows Terminal window and *that window* is nested into a frame with the
  narrator beside it. Your running chat keeps running — the window simply
  changes parent. Close the frame and the terminal is handed straight back to
  the desktop, plain, narrator gone. Nest when you want narration; close when
  you do not.

  ```
  narrate                        # nest THIS terminal + narrator
  narrate -NewTerminal           # open a fresh terminal instead of nesting
  narrate -PanelPercent 40       # wider narrator column
  narrate -Hwnd <handle>         # nest one specific window
  app-shell.bat                  # same thing; from Explorer it opens a new terminal
  ```

  A host window **adopts** both panes with `SetParent`: the real Windows
  Terminal on the left, the narrator's Edge app window on the right, draggable
  divider, one taskbar entry. Adoption rather than re-implementation is the
  point — Windows Terminal keeps its tabs, panes, profiles and keybindings, so
  a new chat is just a new tab and the narrator follows whichever is active.

  Invoking it does not tie up the shell you typed in: pass 1 captures the
  target window and relaunches itself detached, because the window-owning
  process blocks until the frame closes and would otherwise leave the nested
  pane sitting at a busy prompt.

  Release is careful, because the adopted pane is usually a live chat. The
  original window style is saved and restored exactly; the terminal is handed
  back on normal close, on an error during adoption, and in a `finally` around
  the message loop. Verified: after a nest/close cycle the window is alive,
  `parent=0`, style byte-identical (`0x14CF0000`). Diagnostics land in
  `%TEMP%\thinking-narrator-shell.log`.

  Needs no dependencies beyond what Windows already has — Windows Terminal,
  Edge, and WinForms. Two shims are installed to `~\.local\bin` (already on
  PATH, alongside `claude.exe`): `narrate.cmd` for PowerShell and cmd, and an
  extensionless `narrate` for Git Bash, which resolves a bare name to `.exe`
  but never to `.cmd`.

  **Two-window layout (v9):** `launch-app.bat` is the same arrangement without
  reparenting — two separate windows snapped side by side. Kept as the
  fallback if window adoption misbehaves. Verified 2026-08-12 on a 1920×1040
  work area: terminal 1306×1040 at 0,0, narrator 614×1040 at 1306,0.

  ```
  launch-app.bat                                    # 32% narrator column
  powershell -File launch-app.ps1 -PanelPercent 40  # wider narrator
  powershell -File launch-app.ps1 -NoTerminal       # narrator only
  py server.py --panel                              # panel layout, normal browser
  ```

  Placement goes through `SetWindowPos`, not the browser's `--window-size`,
  and the app window runs in its own `--user-data-dir`. Both are required:
  an already-running Edge otherwise opens the app window inside an existing
  process, which leaves no new window handle to position (measured, not
  assumed). Consequence: the panel keeps its own saved voice/mode settings,
  separate from your normal browser profile.

  **Comfort pack (v8):**
  - **Launch:** double-click the desktop shortcut "Thinking Narrator"
    (→ `launch.bat`, minimized console). If the server is already running,
    a second launch just opens the page (connect-probe; Windows
    SO_REUSEADDR makes bind errors unreliable, found in testing).
  - **Keys:** space play/pause · ←/→ seek 5 s · j/k next/prev thought ·
    m mute. Hardware media keys work too (Media Session API), with the
    session title in the Windows media overlay.
  - **Play through:** toggle in the footer — after a thought ends, the next
    one plays automatically; the following block is pre-synthesized while
    the current one speaks, so there is no gap. Turns history into an
    audiobook.
  - **Unread badges:** amber counts on sidebar sessions that gained thoughts
    since you last viewed them (server keeps counts warm in a background
    thread; first-seen sessions start at zero).
  - **Tab state:** ▶ + session title in the tab, amber favicon while
    speaking.
  - **↓ newest** floating button appears when scrolled into history.
  - **Cache cap:** `--cache-mb` (default 200) — oldest MP3s evicted hourly.

  **Karaoke tracking:** synthesis requests `boundary="WordBoundary"` from
  edge-tts and stores per-word timestamps beside each MP3 (`/api/timings`).
  While a thought plays, the exact word being spoken is lit amber, read text
  is bright, unread text is dimmed, and the view auto-scrolls teleprompter-
  style (respects reduced-motion). Seeking/speed changes stay in sync since
  timings are in media time. Words the TTS normalizes (e.g. digits read as
  words) are skipped by the aligner — the highlight just steps over them.
  Custom player bar: play/pause, −10 s, prev/next thought, seek, volume,
  voice, segmented speed — settings persist in localStorage.

- **`app.py`** — the app. Bare launch auto-follows whichever chat is
  currently generating and switches with you between chats; lock it to one
  chat (at launch or at runtime) when you want it pinned. One narrated chat
  at a time, always.
- **`narrate.py`** — the background watcher. Tails every session at once,
  per-session SAPI voices; useful when you want ambient narration of
  every chat simultaneously.

## app.py

```
py app.py                                  # auto-follow the active chat (voice menu)
py app.py --pick                           # choose a session to lock to, via menu
py app.py --session 1 --mode live          # locked to newest session, no prompts
py app.py --session f9fc --mode last:5     # replay last 5 blocks, then follow it live
py app.py --session 1 --mode all --once    # replay full history, then exit
py app.py --kinds thoughts                 # reasoning only (pre-v9 behavior)
py app.py --kinds replies,tools            # skip the reasoning
py app.py --voice-reply en-US-AriaNeural   # second voice for replies
py app.py --list-voices
```

- **`--kinds`** takes a comma-separated list of `thoughts`, `replies`, `tools`
  — or `all` (default) / `both` (thoughts + replies, its pre-tools meaning).
  `--mode` is unrelated: it selects *when* (live vs. history replay).

- **Auto-follow (default):** narrates the session with the newest thinking
  block; when a different chat becomes active it announces the switch and
  follows that one. Internally all transcripts are tailed so a switch never
  misses blocks.
- **Runtime keys (between blocks):** `l` = lock/unlock the currently
  followed chat, `c` = open the session menu and lock to a choice,
  `q` = quit.
- **Lock at launch:** `--session` (list index, session-id prefix, or path)
  or `--pick`; only locked sessions can replay history (`--mode all`,
  `--mode last:N`) since replay needs a definite target.
- Voices: Microsoft Edge neural TTS via `edge-tts` (pip; network required),
  curated menu of 8 en-US/en-GB voices with in-menu preview (`pN`), 47
  en-* voices total. No API key. Offline or on failure it falls back to SAPI
  with a printed warning.
- Playback via winmm MCI, which enables keys: **space** pause/resume,
  **s** skip block, **q** quit (edge engine only; SAPI has no pause).
- `--speed +N%` (default +10), `--engine sapi` to force offline,
  `--newest-only` to drop backlog in live mode (default speaks everything
  in order — skip is a keypress away).
- A scripted run (both `--session` and `--mode` given) never prompts;
  defaults fill in (voice: Christopher).

Dependency: `py -m pip install edge-tts` (installed 2026-07-26; verified
47 en voices, synthesis + MCI playback).

## narrate.py (background multi-chat watcher)

## Verified facts (2026-07-26, desktop "Arath")

- Claude Code appends every assistant message — including `thinking` content
  blocks — to `~/.claude/projects/<project-slug>/<session-id>.jsonl`.
- (2026-08-12) `thinking`, `text`, and `tool_use` blocks share one
  `message.content` list, in the order the CLI displayed them; `text` is the
  printed reply. A live session measured 25 replies to 24 thoughts. **`user`
  records carry `text` blocks too** (the prompts), so reply extraction must
  filter on `type == "assistant"` or it narrates your own words back at you.
- Flush is per message segment, observed to land roughly when that segment's
  tool calls begin executing. Narration therefore lags generation by one
  tool-execution cycle (seconds), not by whole turns. For a final answer with
  no tool calls, the block lands at turn end.
- Stored text is exactly what the CLI displays when expanding thinking; some
  blocks are raw thinking (observed 9.8k chars), others are model-produced
  summaries (observed 184 chars).
- Reading the file while Claude Code holds it open works (observed via
  concurrent grep/parse during a live turn).
- Session titles live in `{"type":"ai-title","aiTitle":...}` records; this
  machine has two SAPI voices (Microsoft David Desktop, Microsoft Zira
  Desktop).

## Usage

```
py narrate.py                 # watch ALL sessions, speak thoughts and replies
py narrate.py --kinds thinking  # reasoning only (pre-v9 behavior)
py narrate.py --dry-run       # print instead of speak
py narrate.py --rate 4        # faster voice (-10..10)
py narrate.py --all           # speak every block instead of skipping to newest
py narrate.py --file <path>   # pin a single transcript
py narrate.py --root <dir> --from-start --once --dry-run --all   # offline test
```

No third-party dependencies. Speech = one blocking PowerShell
`System.Speech.Synthesis.SpeechSynthesizer` call per block.

## Concurrent chats

All transcripts under the projects root are tailed simultaneously (v1 followed
only the newest file and ping-ponged when two chats wrote interleaved — fixed
in v2). Each session gets, in order of first activity:

- a number (`S1`, `S2`, …) and a label — its `aiTitle` if present, else the
  first user prompt, else the filename;
- an installed SAPI voice, assigned round-robin (David, Zira, then repeats).

Once more than one session has produced output, spoken blocks are prefixed
"Session N." so reused voices stay distinguishable. Files created after
startup (new chats) are discovered within ~3 s and read from the beginning;
files existing at startup are read from their end (no replay of history).

## Design choices

- **Backlog policy (default):** speech is slower than generation, so by default
  the queue is drained to the newest block before speaking ("what is it
  thinking *now*" — across all sessions). `--all` reads everything in order.
- **No truncation by default (user ruling 2026-07-26):** full thoughts are
  read, however long. `--max-chars N` is an opt-in cap (cuts at a word
  boundary with an audible "truncated" marker). Consequence: a long raw
  block (9.8k chars observed) is minutes of speech — in `app.py` the `s`
  key skips; in `narrate.py` the drop-backlog default keeps you current.
- **Subagent thinking** (`isSidechain` records) is skipped unless
  `--include-agents`.

## Known limits

- SAPI default voices; code identifiers and math read poorly.
- No pause/skip controls; Ctrl+C stops the narrator.
- Idle historical transcripts are tailed too (cost: one `stat` per file per
  poll — negligible, but the startup count includes them).
- With only two installed voices, three or more concurrent chats share voices;
  the spoken "Session N" prefix is the disambiguator.

Possible extensions: `--voice` pinning per session, edge-tts for natural
voices (network, adds dependency), hotkey skip.
