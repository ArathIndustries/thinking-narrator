#!/usr/bin/env python3
"""Single-chat thinking narrator app.

Interactive launcher: pick one Claude Code session, then live-follow it,
replay its full thinking history, or replay the last N blocks — in a neural
voice. Watches exactly one transcript (no cross-chat scanning); run one
instance per chat you care about.

Engines:
  edge  — Microsoft Edge neural TTS via edge-tts (network, free, smooth).
          Playback through winmm MCI, which enables pause/skip/quit keys.
  sapi  — offline Windows SAPI fallback (robotic, no pause key).

During edge playback: space = pause/resume, s = skip block, q = quit.
"""

import argparse
import asyncio
import ctypes
import glob
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import narrate  # Tail, extract_thinking, clean, session_title, speak

try:
    import edge_tts
    HAVE_EDGE = True
except ImportError:
    HAVE_EDGE = False

try:
    import msvcrt
    KEYS = sys.stdin.isatty()
except ImportError:
    KEYS = False

VOICES = [
    ("en-US-ChristopherNeural", "US male, deep and calm"),
    ("en-US-EricNeural",        "US male, mellow"),
    ("en-US-GuyNeural",         "US male, upbeat"),
    ("en-US-AriaNeural",        "US female, expressive"),
    ("en-US-JennyNeural",       "US female, warm"),
    ("en-US-MichelleNeural",    "US female, even"),
    ("en-GB-RyanNeural",        "UK male"),
    ("en-GB-SoniaNeural",       "UK female"),
]
DEFAULT_VOICE = VOICES[0][0]


class Quit(Exception):
    pass


# ---------- audio ----------

def mci(cmd):
    buf = ctypes.create_unicode_buffer(255)
    err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 254, None)
    if err:
        eb = ctypes.create_unicode_buffer(255)
        ctypes.windll.winmm.mciGetErrorStringW(err, eb, 254)
        raise RuntimeError(f"MCI error {err}: {eb.value} [{cmd}]")
    return buf.value


def play_mp3(path):
    """Play with pause/skip/quit keys. Returns 'done' or 'skipped'."""
    alias = "thoughtblock"
    mci(f'open "{path}" type mpegvideo alias {alias}')
    paused = False
    try:
        mci(f"play {alias}")
        while True:
            if mci(f"status {alias} mode") == "stopped":
                return "done"
            if KEYS and msvcrt.kbhit():
                k = msvcrt.getwch().lower()
                if k == " ":
                    mci(f"{'resume' if paused else 'pause'} {alias}")
                    paused = not paused
                elif k == "s":
                    return "skipped"
                elif k == "q":
                    raise Quit()
            time.sleep(0.1)
    finally:
        try:
            mci(f"close {alias}")
        except RuntimeError:
            pass


def edge_synth(text, voice, speed):
    rate = f"{'+' if speed >= 0 else ''}{speed}%"
    fd, mp3 = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    async def go():
        await edge_tts.Communicate(text, voice, rate=rate).save(mp3)
    asyncio.run(go())
    assert os.path.getsize(mp3) > 0, "edge-tts produced empty audio"
    return mp3


def speak_block(text, args):
    if args.engine in ("auto", "edge") and HAVE_EDGE:
        try:
            mp3 = edge_synth(text, args.voice, args.speed)
        except Exception as e:
            print(f"[warn] edge-tts failed ({e}); falling back to SAPI",
                  file=sys.stderr)
        else:
            try:
                return play_mp3(mp3)
            finally:
                os.unlink(mp3)
    sapi_rate = max(-10, min(10, round(args.speed / 5)))
    sapi_voice = args.voice if args.engine == "sapi" else None
    narrate.speak(text, sapi_rate, sapi_voice)
    return "done"


# ---------- session selection ----------

def list_sessions(root, limit=15):
    files = sorted(glob.glob(os.path.join(root, "*", "*.jsonl")),
                   key=os.path.getmtime, reverse=True)[:limit]
    return [(p,
             time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(p))),
             os.path.basename(os.path.dirname(p)),
             narrate.session_title(p))
            for p in files]


def resolve_session(root, sel):
    if os.path.isfile(sel):
        return sel
    rows = list_sessions(root, limit=50)
    if sel.isdigit() and len(sel) <= 2:
        idx = int(sel)
        assert 1 <= idx <= len(rows), f"index {idx} out of range 1..{len(rows)}"
        return rows[idx - 1][0]
    hits = [p for p, *_ in rows if os.path.basename(p).startswith(sel)]
    assert len(hits) == 1, f"session {sel!r} matched {len(hits)} transcripts"
    return hits[0]


def ask(prompt):
    try:
        return input(prompt).strip()
    except EOFError:
        raise Quit()


def pick_session(root):
    rows = list_sessions(root)
    assert rows, f"no transcripts under {root!r}"
    print("\nRecent sessions:")
    for i, (p, mt, proj, title) in enumerate(rows, 1):
        print(f" {i:2}  {mt}  {proj:<22.22}  {title}")
    while True:
        c = ask("\nSession # (q quits): ").lower()
        if c == "q":
            raise Quit()
        if c.isdigit() and 1 <= int(c) <= len(rows):
            return rows[int(c) - 1][0]


def prompt_mode():
    c = ask("Playback — [Enter] live | a = all history | number = last N blocks: ").lower()
    if c == "":
        return "live", 0
    if c == "a":
        return "all", 0
    if c.isdigit() and int(c) > 0:
        return "last", int(c)
    print("unrecognized, defaulting to live")
    return "live", 0


def prompt_voice(args):
    print("\nVoices:")
    for i, (name, desc) in enumerate(VOICES, 1):
        print(f" {i}  {name:<26} {desc}")
    while True:
        c = ask("Voice # ([Enter] = 1, pN = preview N): ").lower()
        if c == "":
            return DEFAULT_VOICE
        if c.isdigit() and 1 <= int(c) <= len(VOICES):
            return VOICES[int(c) - 1][0]
        if c.startswith("p") and c[1:].isdigit() and 1 <= int(c[1:]) <= len(VOICES):
            name = VOICES[int(c[1:]) - 1][0]
            short = name.split("-")[-1].replace("Neural", "")
            try:
                mp3 = edge_synth(f"This is {short}, reading your Claude's thoughts.",
                                 name, args.speed)
                try:
                    play_mp3(mp3)
                finally:
                    os.unlink(mp3)
            except Exception as e:
                print(f"[warn] preview failed: {e}", file=sys.stderr)


# ---------- main ----------

def parse_mode(s):
    if s in ("live", "all"):
        return s, 0
    if s.startswith("last:") and s[5:].isdigit():
        return "last", int(s[5:])
    raise argparse.ArgumentTypeError("mode must be live, all, or last:N")


def collect(tail, args):
    return [(rec.get("timestamp", ""), t)
            for rec in tail.read_new()
            for t in narrate.extract_thinking(rec, args.include_agents)]


def say(ts, text, args):
    text = narrate.clean(text, args.max_chars)
    print(f"[{ts[11:19] or '--:--:--'}] {text[:100]}{'...' if len(text) > 100 else ''}")
    if not args.dry_run:
        speak_block(text, args)


def main():
    ap = argparse.ArgumentParser(
        description="Narrate one Claude Code chat: live, full replay, or last N blocks.")
    ap.add_argument("--session", help="transcript path, id prefix, or list index")
    ap.add_argument("--mode", type=parse_mode, help="live | all | last:N")
    ap.add_argument("--voice", help="edge voice name (see --list-voices)")
    ap.add_argument("--engine", choices=("auto", "edge", "sapi"), default="auto")
    ap.add_argument("--speed", type=int, default=10,
                    help="speech rate in percent for edge (default +10)")
    ap.add_argument("--root", default=narrate.PROJECTS_ROOT)
    ap.add_argument("--max-chars", type=int, default=0,
                    help="optional cap; 0 = read full thoughts (default)")
    ap.add_argument("--poll", type=float, default=0.5)
    ap.add_argument("--newest-only", action="store_true",
                    help="in live mode, drop backlog and speak only the newest block")
    ap.add_argument("--include-agents", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true",
                    help="exit after replay instead of following live")
    ap.add_argument("--list-voices", action="store_true")
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if args.list_voices:
        for name, desc in VOICES:
            print(f"{name:<26} {desc}")
        if HAVE_EDGE:
            allv = asyncio.run(edge_tts.list_voices())
            others = sorted(v["ShortName"] for v in allv
                            if v["ShortName"].startswith("en-")
                            and v["ShortName"] not in {n for n, _ in VOICES})
            print(f"\n{len(others)} more en-* voices: {', '.join(others)}")
        return

    interactive = sys.stdin.isatty()
    try:
        if args.session:
            path = resolve_session(args.root, args.session)
        else:
            assert interactive, "no TTY: pass --session (plus --mode/--voice as needed)"
            path = pick_session(args.root)
        print(f'[app] session: "{narrate.session_title(path)}"')

        mode, n = args.mode if args.mode else (prompt_mode() if interactive else ("live", 0))

        scripted = bool(args.session and args.mode)
        if not args.voice:
            if (interactive and not scripted and not args.dry_run
                    and HAVE_EDGE and args.engine != "sapi"):
                args.voice = prompt_voice(args)
            else:
                args.voice = DEFAULT_VOICE
        engine = "edge-tts" if (args.engine != "sapi" and HAVE_EDGE) else "SAPI"
        print(f"[app] engine: {engine}, voice: {args.voice}, speed: {args.speed:+d}%")
        if KEYS:
            print("[keys] space = pause/resume, s = skip block, q = quit")

        tail = narrate.Tail(path, mode != "live")
        if mode != "live":
            backlog = collect(tail, args)
            if mode == "last":
                backlog = backlog[-n:]
            print(f"[app] replaying {len(backlog)} block(s)")
            for ts, text in backlog:
                say(ts, text, args)
        if not args.once:
            print("[app] following live (Ctrl+C stops)")
            while True:
                blocks = collect(tail, args)
                if args.newest_only and len(blocks) > 1:
                    blocks = blocks[-1:]
                for ts, text in blocks:
                    say(ts, text, args)
                time.sleep(args.poll)
    except (Quit, KeyboardInterrupt):
        print("\n[app] stopped")


if __name__ == "__main__":
    main()
