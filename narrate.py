#!/usr/bin/env python3
"""Live audio narrator for Claude Code.

Tails every Claude Code session transcript (JSONL under ~/.claude/projects/)
concurrently and speaks each new narratable block through Windows SAPI. Two
kinds are narratable and `--kinds` selects them: `thinking` (the reasoning
the CLI lets you expand) and `text` (the reply printed to the terminal).
Concurrent chats are distinguished by voice (installed SAPI voices are
assigned round-robin in order of first activity) and, when more than one
session is active, a spoken "Session N" prefix.

Also the shared core for app.py and server.py: Tail, extract_blocks,
to_speech, session_title, speak.

Measured behavior (2026-07-26, this machine): Claude Code appends each
assistant message segment to the transcript roughly when that segment's
tool calls begin executing — so narration lags generation by one
tool-execution cycle (seconds), not by whole turns. Blocks may be raw
thinking text or model-produced summaries; the file stores exactly what
the CLI displays.

Zero third-party dependencies: speech runs through a PowerShell
System.Speech call per utterance (blocking, which serializes playback).
"""

import argparse
import glob
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time

PROJECTS_ROOT = os.path.expanduser(os.path.join("~", ".claude", "projects"))


def list_voices():
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() "
        "| ForEach-Object { $_.VoiceInfo.Name }"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=30,
        )
        return [v.strip() for v in r.stdout.splitlines() if v.strip()]
    except Exception as e:
        print(f"[warn] voice enumeration failed, using default voice: {e}",
              file=sys.stderr)
        return []


def session_title(path):
    """Session label: aiTitle record, else first user prompt, else filename."""
    fallback = None
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if '"ai-title"' in line:
                    try:
                        t = json.loads(line).get("aiTitle")
                        if t:
                            return t[:60]
                    except Exception:
                        pass
                elif fallback is None and '"type":"user"' in line:
                    try:
                        rec = json.loads(line)
                        if rec.get("isSidechain"):
                            continue
                        c = rec.get("message", {}).get("content")
                        if isinstance(c, list):
                            c = " ".join(b.get("text", "") for b in c
                                         if isinstance(b, dict) and b.get("type") == "text")
                        if isinstance(c, str) and c.strip() and not c.strip().startswith("<"):
                            fallback = c.strip()[:60]
                    except Exception:
                        pass
    except OSError:
        pass
    return fallback or os.path.basename(path)


KINDS = ("thinking", "text", "tool")

KIND_ALIASES = {
    "thinking": "thinking", "thoughts": "thinking", "thought": "thinking",
    "text": "text", "replies": "text", "reply": "text",
    "tool": "tool", "tools": "tool", "tool_use": "tool",
}


def parse_kinds(s):
    """'thoughts,tools' -> ('thinking', 'tool'). 'all' and 'both' are shortcuts
    ('both' keeps its pre-tool meaning: thinking + replies)."""
    s = (s or "all").strip().lower()
    if s == "all":
        return KINDS
    if s == "both":
        return ("thinking", "text")
    out = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        assert part in KIND_ALIASES, \
            f"unknown kind {part!r}; use any of thoughts, replies, tools (or all/both)"
        k = KIND_ALIASES[part]
        if k not in out:
            out.append(k)
    assert out, "no kinds selected"
    return tuple(out)


# Spoken form per tool. Gerunds because these are read aloud mid-work
# ("Editing index.html" scans better than "Edit index.html"), and basenames
# because a full Windows path is unlistenable read character by character.
TOOL_VERBS = {
    "Read": "Reading", "Edit": "Editing", "Write": "Writing",
    "NotebookEdit": "Editing notebook",
}


def summarize_tool(block):
    """One short spoken line for a tool call: what it is doing, to what.

    Deliberately not the arguments — the point is glanceable narration of the
    work, so this reads the one field that identifies the target and drops the
    rest. Returns "" for a call with nothing worth saying.
    """
    name = block.get("name") or "tool"
    inp = block.get("input")
    if not isinstance(inp, dict):
        inp = {}

    def base(p):
        return os.path.basename(str(p).rstrip("/\\")) or str(p)

    if name in TOOL_VERBS and inp.get("file_path"):
        return f"{TOOL_VERBS[name]} {base(inp['file_path'])}"
    if name in ("Bash", "PowerShell"):
        what = inp.get("description") or inp.get("command") or ""
        what = re.sub(r"\s+", " ", str(what)).strip()
        return f"Running: {what[:110]}" if what else "Running a command"
    if name == "Grep":
        where = f" in {base(inp['path'])}" if inp.get("path") else ""
        return f"Searching for {inp.get('pattern', 'a pattern')}{where}"
    if name == "Glob":
        return f"Finding files matching {inp.get('pattern', '')}".strip()
    if name in ("Task", "Agent"):
        return f"Launching an agent: {inp.get('description', 'subtask')}"
    if name in ("WebFetch", "WebSearch"):
        target = inp.get("url") or inp.get("query") or ""
        m = re.match(r"https?://([^/]+)", str(target))
        return f"Fetching {m.group(1) if m else str(target)[:80]}"
    if name == "TodoWrite":
        return "Updating the task list"
    if name == "Skill":
        return f"Loading the {inp.get('skill', '')} skill".replace("  ", " ")
    if inp.get("file_path"):
        return f"{name} on {base(inp['file_path'])}"
    return f"Calling {name}"


def extract_blocks(rec, include_agents, kinds=KINDS):
    """Yield (kind, text) pairs from one transcript record, in CLI order.

    kind "thinking" = a reasoning block (what the CLI expands); kind "text" =
    the assistant's printed reply. Both live in the same `message.content`
    list, interleaved with `tool_use` blocks, in the order they were shown.

    The `type == "assistant"` guard is load-bearing for "text": user records
    carry text content too (the prompts), and narrating those back would echo
    Arath to himself. Thinking blocks only ever appear on assistant records,
    so the guard costs nothing there.
    """
    if rec.get("isSidechain") and not include_agents:
        return []
    if rec.get("type") != "assistant":
        return []
    msg = rec.get("message")
    if not isinstance(msg, dict) or not isinstance(msg.get("content"), list):
        return []
    out = []
    for b in msg["content"]:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t in ("thinking", "text"):
            if t in kinds and isinstance(b.get(t), str) and b[t].strip():
                out.append((t, b[t]))
        elif t == "tool_use" and "tool" in kinds:
            # A tool call has no prose of its own, so the summary IS the block
            # text: what the card shows is exactly what gets spoken, which
            # makes word alignment (D6) exact for this kind by construction.
            s = summarize_tool(b)
            if s:
                out.append(("tool", s))
    return out


def extract_thinking(rec, include_agents):
    """Thinking blocks only — kept for callers that never wanted replies."""
    return [t for kind, t in extract_blocks(rec, include_agents, ("thinking",))]


class Tail:
    """Incremental reader that only yields complete lines."""

    def __init__(self, path, from_start):
        self.path = path
        self.pos = 0 if from_start else os.path.getsize(path)
        self.buf = b""

    def read_new(self):
        size = os.path.getsize(self.path)
        if size < self.pos:  # file truncated or replaced
            self.pos, self.buf = 0, b""
        if size == self.pos:
            return []
        with open(self.path, "rb") as f:
            f.seek(self.pos)
            chunk = f.read()
            self.pos = f.tell()
        lines = (self.buf + chunk).split(b"\n")
        self.buf = lines.pop()  # trailing partial line, kept for next poll
        out = []
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw.decode("utf-8")))
            except Exception as e:
                print(f"[warn] unparseable transcript line: {e}", file=sys.stderr)
        return out


def clean(text, max_chars):
    text = re.sub(r"`+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if max_chars and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + " ... truncated"
    return text


CODE_FENCE = re.compile(r"^[ \t]*(```|~~~).*?(?:^[ \t]*\1[ \t]*$|\Z)", re.S | re.M)


def strip_markdown(text):
    """Markdown → speakable prose, for printed replies.

    Two rules govern every substitution here, because the karaoke aligner
    (D6) matches each spoken word forward through the *raw* text with
    indexOf: (1) markers are deleted but their words are kept, so every
    spoken word still exists in the card; (2) nothing is ever *added* — an
    injected word like "code block" would have no counterpart in the raw
    text and would drag the highlight cursor to a false match. Fenced code
    is therefore dropped silently; the card still shows it.
    """
    text = CODE_FENCE.sub(" ", text)
    text = re.sub(r"^ {0,3}#{1,6} +", "", text, flags=re.M)           # headings
    text = re.sub(r"^ *>+ ?", "", text, flags=re.M)                   # quotes
    text = re.sub(r"^ *([-*+]|\d+[.)]) +", "", text, flags=re.M)      # list markers
    text = re.sub(r"^ *[-*_]{3,} *$", " ", text, flags=re.M)          # rules
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)            # links/images
    text = re.sub(r"^ *\|[-: |]+\| *$", " ", text, flags=re.M)        # table rules
    text = text.replace("|", ", ")                                    # table cells
    text = re.sub(r"\*\*|~~|\*", "", text)                            # emphasis
    return text
    # NB: single "_" is deliberately left alone — snake_case identifiers are
    # far more common in this corpus than _italics_.


def to_speech(text, kind="thinking", max_chars=0):
    """The exact string handed to the synthesizer, per block kind.

    Never returns "": a reply that is nothing but a fenced code block cleans
    to empty, and every engine here treats empty input as a hard error
    (edge-tts returns zero bytes; SAPI speaks nothing). The marker keeps the
    block audible and countable. It lives here rather than in each caller so
    all three entry points behave the same.
    """
    if kind == "text":
        text = strip_markdown(text)
    return clean(text, max_chars) or "Code block."


def speak(text, rate, voice=None):
    fd, tmp = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8-sig") as f:
            f.write(text)
        sel = f"try {{ $s.SelectVoice('{voice}') }} catch {{ }}; " if voice else ""
        ps = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"{sel}"
            f"$s.Rate = {rate}; "
            f"$s.Speak([IO.File]::ReadAllText('{tmp}')) | Out-Null"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            check=False,
        )
    finally:
        os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser(
        description="Speak Claude Code thinking blocks as they are written, "
                    "across all concurrent sessions."
    )
    ap.add_argument("--file", help="pin one transcript instead of watching all")
    ap.add_argument("--root", default=PROJECTS_ROOT,
                    help="projects root to scan (default ~/.claude/projects)")
    ap.add_argument("--from-start", action="store_true",
                    help="process whole file(s), not just new content "
                    "(sensible only with --file or a test --root)")
    ap.add_argument("--once", action="store_true",
                    help="process current content then exit (testing)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print blocks instead of speaking")
    ap.add_argument("--all", action="store_true",
                    help="speak every block; default drops backlog, speaks newest only")
    ap.add_argument("--include-agents", action="store_true",
                    help="also narrate subagent (sidechain) thinking")
    ap.add_argument("--kinds", default="all",
                    help="comma-separated: thoughts, replies, tools; or all "
                         "(default) / both (thoughts+replies)")
    ap.add_argument("--rate", type=int, default=2,
                    help="SAPI speech rate, -10..10 (default 2)")
    ap.add_argument("--max-chars", type=int, default=0,
                    help="optional cap; 0 = read full thoughts (default)")
    ap.add_argument("--poll", type=float, default=0.5,
                    help="poll interval in seconds (default 0.5)")
    args = ap.parse_args()
    assert -10 <= args.rate <= 10, "rate outside SAPI range -10..10"

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace",
                               line_buffering=True)

    kinds = parse_kinds(args.kinds)
    voices = list_voices()
    q = queue.Queue()

    def watcher():
        tails = {}
        meta = {}       # path -> {"num", "voice", "label"}, set on first activity
        if args.file:
            assert os.path.isfile(args.file), f"no transcript: {args.file!r}"
            tails[args.file] = Tail(args.file, args.from_start)
            print(f"[narrator] watching {args.file}")
        else:
            for p in glob.glob(os.path.join(args.root, "*", "*.jsonl")):
                tails[p] = Tail(p, args.from_start)
            assert tails, f"no transcripts under {args.root!r}"
            print(f"[narrator] watching {len(tails)} transcript(s) under {args.root} "
                  f"(voices: {', '.join(voices) or 'default only'})")
        last_scan = time.time()
        while True:
            for path, tail in sorted(tails.items()):
                try:
                    recs = tail.read_new()
                except OSError:
                    del tails[path]
                    continue
                blocks = [(rec.get("timestamp", ""), kind, t)
                          for rec in recs
                          for kind, t in extract_blocks(rec, args.include_agents,
                                                        kinds)]
                if not blocks:
                    continue
                if path not in meta:
                    num = len(meta) + 1
                    voice = voices[(num - 1) % len(voices)] if voices else None
                    meta[path] = {"num": num, "voice": voice,
                                  "label": session_title(path)}
                    print(f"[narrator] session {num} = \"{meta[path]['label']}\" "
                          f"({voice or 'default voice'}) — {os.path.basename(path)}")
                m = meta[path]
                for ts, kind, t in blocks:
                    q.put((ts, m["num"], m["voice"], kind, t))
            if args.once:
                q.put(None)
                return
            if not args.file and time.time() - last_scan > 3:
                last_scan = time.time()
                for p in glob.glob(os.path.join(args.root, "*", "*.jsonl")):
                    if p not in tails:
                        # created after startup -> nothing to skip, read from 0
                        tails[p] = Tail(p, from_start=True)
            time.sleep(args.poll)

    threading.Thread(target=watcher, daemon=True).start()

    spoken = 0
    sessions_seen = set()
    try:
        while True:
            item = q.get()
            if item is None:
                break
            stop = False
            if not args.all:
                try:
                    while True:
                        nxt = q.get_nowait()
                        if nxt is None:
                            stop = True
                            break
                        sessions_seen.add(item[1])
                        item = nxt  # keep only the newest queued block
                except queue.Empty:
                    pass
            ts, num, voice, kind, text = item
            sessions_seen.add(num)
            text = to_speech(text, kind, args.max_chars)
            spoken += 1
            tag = {"text": "reply", "tool": "tool"}.get(kind, "thought")
            print(f"[{ts}] S{num} {tag}: {text[:100]}{'...' if len(text) > 100 else ''}")
            if not args.dry_run:
                spoken_text = f"Session {num}. {text}" if len(sessions_seen) > 1 else text
                speak(spoken_text, args.rate, voice)
            if stop:
                break
    except KeyboardInterrupt:
        pass
    print(f"[narrator] done, {spoken} block(s) from {len(sessions_seen)} session(s)")


if __name__ == "__main__":
    main()
