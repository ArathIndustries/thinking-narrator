#!/usr/bin/env python3
"""Live audio narrator for Claude Code thinking blocks.

Tails a Claude Code session transcript (JSONL under ~/.claude/projects/)
and speaks each new `thinking` content block through Windows SAPI.

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


def newest_jsonl(root):
    """Newest session transcript: <projects>/<project-slug>/<session>.jsonl."""
    files = glob.glob(os.path.join(root, "*", "*.jsonl"))
    return max(files, key=os.path.getmtime) if files else None


def extract_thinking(rec, include_agents):
    if rec.get("isSidechain") and not include_agents:
        return []
    msg = rec.get("message")
    if not isinstance(msg, dict) or not isinstance(msg.get("content"), list):
        return []
    return [
        b["thinking"]
        for b in msg["content"]
        if isinstance(b, dict) and b.get("type") == "thinking" and b.get("thinking")
    ]


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


def speak(text, rate):
    fd, tmp = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8-sig") as f:
            f.write(text)
        ps = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
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
        description="Speak Claude Code thinking blocks as they are written."
    )
    ap.add_argument("--file", help="transcript to watch (default: newest session)")
    ap.add_argument("--from-start", action="store_true",
                    help="process the whole file, not just new content")
    ap.add_argument("--once", action="store_true",
                    help="process current content then exit (testing)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print blocks instead of speaking")
    ap.add_argument("--all", action="store_true",
                    help="speak every block; default drops backlog, speaks newest only")
    ap.add_argument("--include-agents", action="store_true",
                    help="also narrate subagent (sidechain) thinking")
    ap.add_argument("--rate", type=int, default=2,
                    help="SAPI speech rate, -10..10 (default 2)")
    ap.add_argument("--max-chars", type=int, default=1500,
                    help="truncate blocks longer than this; 0 = no limit (default 1500)")
    ap.add_argument("--poll", type=float, default=0.5,
                    help="poll interval in seconds (default 0.5)")
    args = ap.parse_args()
    assert -10 <= args.rate <= 10, "rate outside SAPI range -10..10"

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    path = args.file or newest_jsonl(PROJECTS_ROOT)
    assert path and os.path.isfile(path), f"no transcript found: {path!r}"
    print(f"[narrator] watching {path}")

    q = queue.Queue()
    started = time.time()

    def watcher():
        nonlocal path
        tail = Tail(path, args.from_start)
        last_scan = 0.0
        while True:
            for rec in tail.read_new():
                for t in extract_thinking(rec, args.include_agents):
                    q.put((rec.get("timestamp", ""), t))
            if args.once:
                q.put(None)
                return
            # Follow the newest session unless a file was pinned explicitly.
            if not args.file and time.time() - last_scan > 3:
                last_scan = time.time()
                newest = newest_jsonl(PROJECTS_ROOT)
                if newest and newest != path:
                    path = newest
                    fresh = os.path.getctime(path) >= started
                    tail = Tail(path, from_start=fresh)
                    print(f"[narrator] switched to {path}")
            time.sleep(args.poll)

    threading.Thread(target=watcher, daemon=True).start()

    spoken = 0
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
                        item = nxt  # keep only the newest queued block
                except queue.Empty:
                    pass
            ts, text = item
            text = clean(text, args.max_chars)
            spoken += 1
            print(f"[{ts}] {text[:100]}{'...' if len(text) > 100 else ''}")
            if not args.dry_run:
                speak(text, args.rate)
            if stop:
                break
    except KeyboardInterrupt:
        pass
    print(f"[narrator] done, {spoken} block(s)")


if __name__ == "__main__":
    main()
