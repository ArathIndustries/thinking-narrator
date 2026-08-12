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
- MP3 + timings cache key embeds a version prefix (now `wb3|`, was `wb2|`); bump it whenever synthesis output changes shape **or whenever `idx` changes meaning**, or stale entries serve the wrong audio.
- `user` transcript records contain `text` content blocks (the prompts). Reply extraction must filter `rec["type"] == "assistant"` or the narrator reads Arath's own prompts back to him. Thinking-only extraction never needed this guard, so it is easy to omit.
- `to_speech()` never returns `""` — a reply that is only a fenced code block cleans to empty, and edge-tts returns zero bytes for empty input (SAPI speaks nothing). The "Code block." fallback lives in `to_speech`, not in the callers; putting it in `server.py` alone left both CLIs silently mute on those blocks (found 2026-08-12).
- Launching a chromeless Edge app window: pass `--user-data-dir`, or an already-running Edge opens the window inside an **existing** process — no new PID, no new `MainWindowHandle`, so any placement poll times out (measured 2026-08-12). Position with `SetWindowPos` after launch; `--window-size`/`--window-position` alone are unreliable.
- Any spoken word must exist in the raw block text, in order — the karaoke aligner (D6) scans forward with `indexOf`. Never add words to speech text; only delete markers.

### Window adoption (app-shell.ps1, all measured 2026-08-12)

- **`Get-Command wt.exe` returns nothing in a nested non-interactive shell** — the WindowsApps execution alias is not on PATH there. Same trap as `winget` in the hub gotchas. Resolve `%LOCALAPPDATA%\Microsoft\WindowsApps\wt.exe` explicitly. A silent fallback path hid this for two runs; make the fallback print.
- **Windows Terminal opens new windows inside its EXISTING process** — no new PID, no new `MainWindowHandle`. Detect by enumerating top-level windows of class `CASCADIA_HOSTING_WINDOW_CLASS` and diffing, never by process. Pass `-w new` or wt may add a tab to the window Arath is already working in — which adoption would then steal.
- **Edge does the same for a given `--user-data-dir`**: a second `--app` launch is handed to the process that already owns the profile. Find it by command line (`--app=` present, `--type=` absent = the browser process, not a renderer).
- **Restyle before reparenting**: clear `WS_POPUP`/`WS_CAPTION`/`WS_THICKFRAME` and set `WS_CHILD`, then `SetParent`. Keep the original style so closing can restore it.
- **`SetFocus` alone does nothing across processes** — focus is per input queue. Wrap it in `AttachThreadInput(me, targetThread, true/false)`.
- **An adopted window dies with its host.** Any failure after adoption must `SetParent(NULL)` + restore style before rethrowing, or a live chat is destroyed by an unrelated error.

## Key file paths

- Web player (main entrance): `server.py` + `index.html`, launched by `launch.bat` / desktop shortcut "Thinking Narrator"
- Side-by-side app layout: `launch-app.bat` → `launch-app.ps1` (terminal left, `?panel=1` narrator right)
- CLI single-chat app: `app.py`; ambient multi-chat watcher: `narrate.py` (shared core Tail/extract/clean/speak lives in `narrate.py`)
- Data source: `~\.claude\projects\<slug>\<session>.jsonl` (read-only tail)
- MP3/timings cache: `%TEMP%\thinking-narrator-cache\` (hourly eviction, `--cache-mb`, default 200)

## External references

- Repo: https://github.com/ArathIndustries/thinking-narrator (private)
- Player: http://127.0.0.1:8917 (localhost only)
