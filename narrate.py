#!/usr/bin/env python3
"""Live audio narrator for Claude Code thinking blocks.

Tails every Claude Code session transcript (JSONL under ~/.claude/projects/)
concurrently and speaks each new `thinking` content block through Windows
SAPI. Concurrent chats are distinguished by voice (installed SAPI voices are
assigned round-robin in order of first activity) and, when more than one
session is active, a spoken "Session N" prefix.

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
                blocks = [(rec.get("timestamp", ""), t)
                          for rec in recs
                          for t in extract_thinking(rec, args.include_agents)]
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
                for ts, t in blocks:
                    q.put((ts, m["num"], m["voice"], t))
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
            ts, num, voice, text = item
            sessions_seen.add(num)
            text = clean(text, args.max_chars)
            spoken += 1
            print(f"[{ts}] S{num} {text[:100]}{'...' if len(text) > 100 else ''}")
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
