# thinking-narrator — Routing

**Purpose:** this file is the project-level Inputs table. When Claude is working on this project, read this file first to decide what else to load.

For the full spec, see `C:\Users\Arath\OneDrive\Claude Memory\CONVENTIONS.md` §5.1.

---

## Inputs

| Task type              | Files to load                                                     |
|------------------------|-------------------------------------------------------------------|
| Current status         | SNAPSHOT.md                                                       |
| Why this exists        | VISION.md                                                         |
| Next steps             | ROADMAP.md                                                        |
| Decision history       | DECISIONS.md                                                      |
| Session history        | INDEX.md → follow links to central sessions/summaries/            |
| Build story / blog raw material | ../LESSONS.md                                            |
| Actual code            | C:\Users\Arath\Automation_Station\Projects\thinking-narrator\     |

## Known gotchas

- edge-tts 7.2.8 defaults to `SentenceBoundary`; word-level karaoke requires `boundary="WordBoundary"` explicitly.
- Windows + `http.server`: `SO_REUSEADDR` lets a second bind on a live port succeed silently — port-in-use must be detected with a connect probe, never by catching `OSError` on bind.
- Testing from Git Bash: `$variables` inside double-quoted PowerShell one-liners get eaten by bash — use the PowerShell tool or Python `subprocess` list-args.
- Force-killing a Python process with redirected stdout loses the buffer; both entry points set `line_buffering=True`, keep it.
- MP3 + timings cache key embeds a version prefix (`wb2|`); bump it whenever synthesis output changes shape, or stale cache entries serve.

## Key file paths

- Web player (main entrance): `server.py` + `index.html`, launched by `launch.bat` / desktop shortcut "Thinking Narrator"
- CLI single-chat app: `app.py`; ambient multi-chat watcher: `narrate.py` (shared core Tail/extract/clean/speak lives in `narrate.py`)
- Data source: `~\.claude\projects\<slug>\<session>.jsonl` (read-only tail)
- MP3/timings cache: `%TEMP%\thinking-narrator-cache\` (hourly eviction, `--cache-mb`, default 200)

## External references

- Repo: https://github.com/ArathIndustries/thinking-narrator (private)
- Player: http://127.0.0.1:8917 (localhost only)
