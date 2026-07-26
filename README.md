# thinking-narrator

Speaks Claude Code `thinking` blocks aloud, near-live or as history replay.
Two entry points:

- **`app.py`** — the single-chat app. Interactive: lists recent sessions,
  you pick one, choose live-follow / full replay / last-N-blocks, and pick a
  neural voice. Watches exactly one transcript; run one instance per chat.
- **`narrate.py`** — the background watcher. Tails every session at once,
  per-session SAPI voices; useful when you want ambient narration of
  whatever any chat is thinking.

## app.py

```
py app.py                                  # interactive: pick session, mode, voice
py app.py --session 1 --mode live          # newest session, live, no prompts
py app.py --session f9fc --mode last:5     # replay last 5 blocks, then follow live
py app.py --session 1 --mode all --once    # replay full history, then exit
py app.py --list-voices
```

- `--session` = list index, session-id prefix, or a full path.
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
py narrate.py                 # watch ALL sessions, speak new thinking blocks
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
