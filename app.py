#!/usr/bin/env python3
"""Thinking narrator app: follows the chat you're working in.

Default (bare launch): auto-follow — narrates whichever Claude Code chat is
currently generating thinking, and switches when a different chat becomes
active. Runtime keys let you lock to the current chat, unlock back to
auto-follow, or pick a specific session to lock onto. Only one chat is ever
narrated at a time.

Pinned start: `--session <idx|id-prefix|path>` (or `--pick` for the menu)
locks from launch and enables history replay via `--mode all` / `--mode
last:N` before following live.

Engines:
  edge  — Microsoft Edge neural TTS via edge-tts (network, free, smooth).
          Playback through winmm MCI, which enables the playback keys.
  sapi  — offline Windows SAPI fallback (robotic, no pause key).

Keys during playback: space = pause/resume, s = skip block, q = quit.
Keys between blocks:  l = lock/unlock current chat, c = choose chat, q = quit.
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


def speak_block(text, args, voice=None):
    voice = voice or args.voice
    if args.engine in ("auto", "edge") and HAVE_EDGE:
        try:
            mp3 = edge_synth(text, voice, args.speed)
        except Exception as e:
            print(f"[warn] edge-tts failed ({e}); falling back to SAPI",
                  file=sys.stderr)
        else:
            try:
                return play_mp3(mp3)
            finally:
                os.unlink(mp3)
    sapi_rate = max(-10, min(10, round(args.speed / 5)))
    sapi_voice = voice if args.engine == "sapi" else None
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
        c = ask("\nSession # (q cancels): ").lower()
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


# ---------- following ----------

def collect(tail, args):
    return [(rec.get("timestamp", ""), kind, t)
            for rec in tail.read_new()
            for kind, t in narrate.extract_blocks(rec, args.include_agents,
                                                  args.kind_tuple)]


class Follower:
    """Tails every transcript; narrates exactly one — auto-chosen or locked."""

    def __init__(self, root, args):
        self.root = root
        self.args = args
        self.tails = {p: narrate.Tail(p, False)
                      for p in glob.glob(os.path.join(root, "*", "*.jsonl"))}
        self.active = None
        self.locked = False
        self._last_scan = time.time()

    def lock_to(self, path):
        if path not in self.tails:
            self.tails[path] = narrate.Tail(path, False)
        self.active, self.locked = path, True
        print(f'[app] locked to: "{narrate.session_title(path)}"')

    def toggle_lock(self):
        if self.locked:
            self.locked = False
            print("[app] unlocked — auto-follow")
        else:
            self.locked = True
            t = (narrate.session_title(self.active) if self.active
                 else "next chat that generates")
            print(f'[app] locked to: "{t}"')

    def poll(self):
        # pick up chats started after launch
        if time.time() - self._last_scan > 3:
            self._last_scan = time.time()
            for p in glob.glob(os.path.join(self.root, "*", "*.jsonl")):
                if p not in self.tails:
                    self.tails[p] = narrate.Tail(p, from_start=True)
        per = {}
        for path, tail in list(self.tails.items()):
            try:
                blocks = collect(tail, self.args)
            except OSError:
                del self.tails[path]
                continue
            if blocks:
                per[path] = blocks
        if not per:
            return []
        if self.locked and self.active:
            return per.get(self.active, [])
        # auto: the session with the newest block wins
        newest = max(per, key=lambda p: per[p][-1][0])
        if newest != self.active:
            self.active = newest
            print(f'[app] following: "{narrate.session_title(newest)}"')
        return per[self.active]


def handle_idle_keys(follower):
    if not KEYS:
        return
    while msvcrt.kbhit():
        k = msvcrt.getwch().lower()
        if k == "q":
            raise Quit()
        elif k == "l":
            follower.toggle_lock()
        elif k == "c":
            try:
                follower.lock_to(pick_session(follower.root))
            except Quit:
                print("[app] pick cancelled")


# ---------- main ----------

def parse_mode(s):
    if s in ("live", "all"):
        return s, 0
    if s.startswith("last:") and s[5:].isdigit():
        return "last", int(s[5:])
    raise argparse.ArgumentTypeError("mode must be live, all, or last:N")


def say(ts, kind, text, args):
    text = narrate.to_speech(text, kind, args.max_chars)
    tag = "reply" if kind == "text" else "thought"
    print(f"[{ts[11:19] or '--:--:--'}] {tag}: "
          f"{text[:100]}{'...' if len(text) > 100 else ''}")
    if not args.dry_run:
        speak_block(text, args,
                    args.voice_reply if kind == "text" else args.voice)


def main():
    ap = argparse.ArgumentParser(
        description="Narrate the chat you're in: auto-follow the active chat, "
                    "or lock to one (runtime keys or --session).")
    ap.add_argument("--session", help="lock from launch: index, id prefix, or path")
    ap.add_argument("--pick", action="store_true",
                    help="lock from launch via the interactive session menu")
    ap.add_argument("--mode", type=parse_mode,
                    help="live | all | last:N (history replay needs --session/--pick)")
    ap.add_argument("--voice", help="edge voice name (see --list-voices)")
    ap.add_argument("--kinds", choices=("thinking", "text", "both"), default="both",
                    help="read thinking blocks, printed replies, or both (default)")
    ap.add_argument("--voice-reply",
                    help="separate voice for printed replies, so thought and "
                         "reply are distinguishable by ear (default: --voice)")
    ap.add_argument("--engine", choices=("auto", "edge", "sapi"), default="auto")
    ap.add_argument("--speed", type=int, default=10,
                    help="speech rate in percent for edge (default +10)")
    ap.add_argument("--root", default=narrate.PROJECTS_ROOT)
    ap.add_argument("--max-chars", type=int, default=0,
                    help="optional cap; 0 = read full thoughts (default)")
    ap.add_argument("--poll", type=float, default=0.5)
    ap.add_argument("--newest-only", action="store_true",
                    help="drop backlog, speak only the newest pending block")
    ap.add_argument("--include-agents", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--once", action="store_true",
                    help="exit after replay instead of following live")
    ap.add_argument("--list-voices", action="store_true")
    args = ap.parse_args()
    args.kind_tuple = narrate.KINDS if args.kinds == "both" else (args.kinds,)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace",
                               line_buffering=True)

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
        pinned = None
        if args.session:
            pinned = resolve_session(args.root, args.session)
        elif args.pick:
            assert interactive, "--pick needs a TTY"
            pinned = pick_session(args.root)
        assert pinned or not (args.mode or args.once), \
            "--mode/--once need --session or --pick"

        mode, n = ("live", 0)
        if pinned:
            print(f'[app] locked to: "{narrate.session_title(pinned)}"')
            if args.mode:
                mode, n = args.mode
            elif interactive and args.pick:
                mode, n = prompt_mode()

        scripted = bool(args.session and args.mode)
        if not args.voice:
            if (interactive and not scripted and not args.dry_run
                    and HAVE_EDGE and args.engine != "sapi"):
                args.voice = prompt_voice(args)
            else:
                args.voice = DEFAULT_VOICE
        args.voice_reply = args.voice_reply or args.voice
        engine = "edge-tts" if (args.engine != "sapi" and HAVE_EDGE) else "SAPI"
        print(f"[app] engine: {engine}, voice: {args.voice}, speed: {args.speed:+d}%")
        print(f"[app] reading: {args.kinds}"
              + (f", reply voice: {args.voice_reply}"
                 if args.voice_reply != args.voice else ""))

        follower = Follower(args.root, args)
        if pinned:
            tail = narrate.Tail(pinned, mode != "live")
            if mode != "live":
                backlog = collect(tail, args)
                if mode == "last":
                    backlog = backlog[-n:]
                print(f"[app] replaying {len(backlog)} block(s)")
                for ts, kind, text in backlog:
                    say(ts, kind, text, args)
                if args.once:
                    print("[app] done")
                    return
            follower.tails[pinned] = tail  # keep read position; no re-replay
            follower.active, follower.locked = pinned, True
        else:
            print("[app] auto-follow: narrating whichever chat is generating")
        if KEYS:
            print("[keys] space pause | s skip | q quit | l lock/unlock | c choose chat")
        print("[app] following (Ctrl+C stops)")
        while True:
            handle_idle_keys(follower)
            blocks = follower.poll()
            if args.newest_only and len(blocks) > 1:
                blocks = blocks[-1:]
            for ts, kind, text in blocks:
                say(ts, kind, text, args)
            time.sleep(args.poll)
    except (Quit, KeyboardInterrupt):
        print("\n[app] stopped")


if __name__ == "__main__":
    main()
