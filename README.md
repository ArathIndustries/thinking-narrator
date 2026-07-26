# thinking-narrator

Tails the live Claude Code session transcript and speaks each new `thinking`
block through Windows SAPI. Run it in a second terminal while working in a
Claude Code chat; it narrates the model's thinking near-live.

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

## Usage

```
py narrate.py                 # watch newest session, speak new thinking blocks
py narrate.py --dry-run       # print instead of speak
py narrate.py --rate 4        # faster voice (-10..10)
py narrate.py --all           # speak every block instead of skipping to newest
py narrate.py --file <path>   # pin one transcript; disables newest-session follow
py narrate.py --from-start --once --dry-run --all   # offline test over a full file
```

No third-party dependencies. Speech = one blocking PowerShell
`System.Speech.Synthesis.SpeechSynthesizer` call per block.

## Design choices

- **Backlog policy (default):** speech is slower than generation, so by default
  the queue is drained to the newest block before speaking ("what is it
  thinking *now*"). `--all` reads everything in order instead.
- **Truncation:** blocks over `--max-chars` (default 1500 ≈ 75 s of speech) are
  cut at a word boundary with an audible "truncated" marker.
- **Session follow:** with no `--file`, the watcher re-scans every 3 s and hops
  to the newest transcript, so it survives starting a new chat session.
- **Subagent thinking** (`isSidechain` records) is skipped unless
  `--include-agents`.

## Known limits

- SAPI default voice; code identifiers and math read poorly.
- No pause/skip controls; Ctrl+C stops the narrator.
- A block interrupted mid-truncation boundary is spoken once, never resumed.

Possible extensions: `--voice` selection, edge-tts for natural voices (network,
adds dependency), hotkey skip.
