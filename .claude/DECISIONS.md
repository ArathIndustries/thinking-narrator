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

## 2026-08-12 — D10: Replies are a second block *kind*, not a second feed

Arath asked for the printed responses to be readable too, switchable between thoughts / replies / both. Implemented as one append-only list per session carrying both kinds tagged `kind`, rather than two parallel lists. Reasons: the interleaving (think → print → think) is the thing worth listening to and only a single ordered list preserves it; `idx` stays a stable handle for the audio cache and `?after=` paging; mode becomes a pure client-side filter, so switching is instant and the server stays dumb. Cost, accepted: `idx` no longer means "nth thinking block", so every `wb2|` cache entry is potentially mismapped — cache key bumped to `wb3|` with kind included. Default is **both**, on all three entry points.

## 2026-08-12 — D11: Markdown is stripped for speech, but no word is ever invented

Printed replies are markdown; read literally they are noise ("asterisk asterisk", table pipes, whole code blocks). `strip_markdown` deletes markers and keeps their words. The binding constraint is D6: the karaoke aligner matches each spoken word forward through the **raw** text with `indexOf`, so any *added* word would have no counterpart and would drag the cursor to a false match. Hence fenced code is dropped silently rather than announced. Verified: on fixture and live blocks, 100% of spoken words align (7/7 on a reply mixing prose and a code fence). Single exception, deliberate: a reply that is *only* code has no speakable prose, so `to_speech` returns the marker "Code block." — those words are absent from the card, produce zero spans, and the highlight stays correctly inert.

## 2026-08-12 — D12: The "app" is two real windows, not an embedded terminal

Arath asked to interface with Claude Code in a terminal with the narrator alongside it. Shipped as `launch-app.bat`: Windows Terminal running `claude` on the left, the narrator right in a chromeless Edge app window using a new compact `?panel=1` layout. Rejected for now: embedding a terminal in the page (ConPTY/pywinpty + xterm.js), which would make it one window but adds two dependencies and re-implements a terminal Windows already provides. Revisit if daily use shows the two-window split is the friction. Placement uses `SetWindowPos` after launch and a dedicated `--user-data-dir` — both measured requirements, see ROUTING gotchas.

## 2026-08-12 — D13: Adopt Windows Terminal into a host window (supersedes D12's deferral)

D12 deferred the one-window app and offered the choice; Arath ruled for it immediately — "that way I can keep opening and switching between sessions whenever I want to, plus this terminal app has a lot of useful features." That last clause decided the *implementation*: the xterm.js route would have replaced Windows Terminal with a lesser terminal, losing the tabs that make session-switching work. So `app-shell.ps1` **adopts** the real windows instead — a WinForms host window, Windows Terminal reparented into the left pane via `SetParent`, the narrator's Edge app window into the right, a draggable divider between them. No new dependencies: Windows Terminal, Edge, and WinForms are already on the machine.

Consequences accepted: cross-process reparenting needs styles rewritten to `WS_CHILD` before `SetParent`, and focus needs `AttachThreadInput` (focus is per input queue). Closing the shell **releases** the terminal back to the desktop as a normal window rather than destroying it, so an in-progress chat survives; any error during adoption does the same before rethrowing. Both `launch-app.*` (two windows) and `app-shell.*` (one window) ship — the two-window version stays as the no-reparenting fallback.

## 2026-08-12 — D14: The shell nests the terminal you are already in (refines D13)

D13 shipped a shell that *launched* a terminal. Arath's correction, after using it: "if I'm already in a terminal clicking around, doing some work, is there a way that I could invoke the narrator and take my existing terminal instance and nest it inside of the shell? and then close the shell and just go back to my plain terminal whenever I need to." So nesting-in-place is now the default and the whole thing is a **toggle**: `narrate` from any Windows Terminal window adopts that window; closing the frame hands it back. Launching a new terminal is the fallback for when the invoker is not a terminal (Explorer, a shortcut) or `-NewTerminal` is passed.

Two consequences: (1) the script relaunches itself detached, because the window-owning process blocks in `Application.Run` and would otherwise leave the nested pane at a busy prompt — pass 1 captures the foreground window while it is still foreground, then hands off; (2) since the adopted pane is now usually a **live chat**, release moved into a `finally` around the message loop as well as `FormClosing` and the adoption `catch`. Verified on a throwaway window: after nest → close, the window is alive, `parent=0`, and its style is restored byte-identical (0x14CF0000).

`narrate.cmd` installed to `~\.local\bin` (already on PATH next to `claude.exe`) so it is typeable from anywhere.

## 2026-08-12 — D15: Tool calls are the third kind; the switch becomes toggles

Arath: "could I see all of the commands that you run as well? … I don't need everything that you're doing, but I can see when you run a batch script, I can see when you are updating code, when you're writing or reading or analyzing." So `tool_use` blocks become a third narratable kind, and the mode switch becomes **three independent toggles** rather than presets — that reaches all seven combinations he enumerated without enumerating them.

What gets spoken is a **summary, not the arguments**: gerund plus target, from the one input field that identifies what is being acted on ("Editing index.html", "Running: commit and push", "Searching for extract_blocks in narrate.py"). Two rulings inside that: file paths are reduced to basenames, because a full Windows path read character by character is unlistenable; and `Bash` prefers its `description` field over the command, which is what makes the line read like narration instead of shell. A tool call has no prose of its own, so the summary *is* the block text — the card shows exactly what is spoken, which makes D6 word alignment exact for this kind by construction.

Measured calibration: one real session held **198 tool calls to 54 thoughts and 59 replies** — roughly two thirds of all blocks. Tool narration therefore dominates when enabled, and since speech is slower than generation the queue falls behind faster. Recorded rather than designed around; a separate toggle plus a recessive sage accent is the response, and whether the default should include tools is a Phase 5 question for use to answer.

Cache key bumped `wb3|` → `wb4|`: `idx` shifted again when tool blocks joined the list.

## 2026-07-26 — D9: Blog rulings (Arath, interactive)

Repo flips public **the day the blog post ships** (not before, not never). Post angle: **"I made Claude Code think out loud"** — demo-first story ending at the karaoke player following live reasoning. Venue: **the portfolio site (arath.site)**, pending a page-order/IA review Arath opened in the same ruling session.

## 2026-09-07 — D16: Talk mode — the narrator becomes half of a voice loop

Arath, having verified `/voice` works ("I just hold down the space bar, and you seem to be able to hear me"): "could we wrap all of the 'voice in' and 'narration out' into something similar to how it works on mobile?" The reason given: "being able to talk to you and get you to talk back is where I can start to engage with my course content a little better."

Ruling: no new speech path. Claude Code's own `/voice` (hold Space; Windows default capture device, verified 9/07 = Corsair HS60 headset mic; transcription server-side) is the input, and the narrator is the output. What the narrator needed was a **preset**, not a feature: Replies only, and `narrate.py`'s drop-backlog drain ported into the player as a one-deep queue. Measured 8/12: with Tools on the queue never drains — a loop that must answer what was just said cannot carry a backlog. So `Talk` is a footer toggle (persisted), `?talk=1` forces it (the shell's `-Talk` switch), a hand edit of the kind toggles leaves Talk, and the kinds held before Talk are restored on exit. Play-through is ignored while Talk is on, since walking to the next block is the backlog by another name.

The other half is prompt-level: a `speech-mode` skill (hub `skills/speech-mode/`, body `feedback/feedback_speech_mode_replies.md`) that switches replies to short prose with no lists, paths, code, or tables, because `strip_markdown` deletes markers and drops fences, so layout does not survive into audio.

Absorbs B089 (v10 acid test) into B110: the first real Talk sitting on course material is the acid test, and it answers the "Tools by default" and "drop-backlog in the player" questions by construction — Talk is the setting the use case needed. Not built, deliberately: open-mic barge-in and phone-side audio; neither exists in Claude Code, and a custom speech-to-text path would be a parallel system rather than an extension.
