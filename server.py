#!/usr/bin/env python3
"""Web UI for the thinking narrator.

Serves a localhost player page: session list, scrollable log, and a native
browser audio player — which is what provides pause, scrubbing (rewind),
volume, and speed controls. The server tails transcripts, extracts both
narratable block kinds — `thinking` (reasoning) and `text` (the printed
reply) — and synthesizes per-block MP3s (edge-tts, cached in %TEMP%). Which
kinds actually play is a client-side mode; the server always serves both.

Run: py server.py    → opens http://127.0.0.1:8917 in the default browser.
     py server.py --panel  → compact sidecar layout, for docking beside a
                             terminal (see launch-app.bat).

Endpoints:
  GET /                      player page
  GET /api/sessions          recent sessions, newest first
  GET /api/blocks?session=&after=   blocks (idx, kind, ts, text)
  GET /api/audio?session=&idx=&voice=&rate=   MP3 for one block (Range OK)
  GET /api/timings?session=&idx=&voice=&rate= word timestamps for karaoke
"""

import argparse
import asyncio
import glob
import hashlib
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import narrate

try:
    import edge_tts
    HAVE_EDGE = True
except ImportError:
    HAVE_EDGE = False

DEFAULT_VOICE = "en-US-ChristopherNeural"
CACHE = os.path.join(tempfile.gettempdir(), "thinking-narrator-cache")

ARGS = None
STORE = {}        # path -> {"tail": Tail, "blocks": [{idx, ts, text}]}
ID2PATH = {}
TITLES = {}
SYNTH_LOCKS = {}  # cache key -> Lock, so duplicate requests can't race
LOCK = threading.Lock()


def scan_sessions():
    files = sorted(glob.glob(os.path.join(ARGS.root, "*", "*.jsonl")),
                   key=os.path.getmtime, reverse=True)[:ARGS.limit]
    out = []
    with LOCK:
        for p in files:
            sid = os.path.splitext(os.path.basename(p))[0]
            ID2PATH[sid] = p
            if p not in TITLES:
                TITLES[p] = narrate.session_title(p)
            st = STORE.get(p)
            out.append({"id": sid, "title": TITLES[p],
                        "project": os.path.basename(os.path.dirname(p)),
                        "mtime": int(os.path.getmtime(p)),
                        "blocks": len(st["blocks"]) if st else None})
    return out


def warm_counts():
    """Background: keep every listed session's block count current so the
    sidebar can show unread badges without a client-triggered full parse."""
    while True:
        try:
            scan_sessions()
            with LOCK:
                paths = list(ID2PATH.values())
            for p in paths:
                get_blocks(p)
        except Exception as e:
            print(f"[warn] count warmer: {e}", file=sys.stderr)
        time.sleep(2)


def prune_cache():
    """Background: hourly, evict oldest cache files beyond --cache-mb."""
    while True:
        try:
            files = sorted(((os.path.getmtime(f), f)
                            for f in glob.glob(os.path.join(CACHE, "*"))),
                           reverse=True)
            total = 0
            for _, f in files:
                total += os.path.getsize(f)
                if total > ARGS.cache_mb * 1_000_000:
                    os.unlink(f)
        except Exception as e:
            print(f"[warn] cache prune: {e}", file=sys.stderr)
        time.sleep(3600)


def get_blocks(path):
    """All narratable blocks for one session, thinking and replies together.

    One list, in transcript order, each tagged with its kind — the client
    filters by mode. Keeping both kinds in a single append-only list is what
    lets `idx` stay a stable handle for the audio cache and `?after=`.
    """
    with LOCK:
        st = STORE.get(path)
        if st is None:
            st = STORE[path] = {"tail": narrate.Tail(path, True), "blocks": []}
        for rec in st["tail"].read_new():
            for kind, t in narrate.extract_blocks(rec, ARGS.include_agents):
                st["blocks"].append({"idx": len(st["blocks"]), "kind": kind,
                                     "ts": rec.get("timestamp", ""), "text": t})
        return list(st["blocks"])


def synth(sid, idx, voice, rate):
    """Synthesize one block; returns (mp3_path, timings_path).

    Timings = [{"t": seconds, "w": word}] from edge-tts WordBoundary events,
    cached beside the mp3.
    """
    path = ID2PATH.get(sid)
    if path is None:
        scan_sessions()
        path = ID2PATH.get(sid)
    assert path, f"unknown session {sid!r}"
    blocks = get_blocks(path)
    assert 0 <= idx < len(blocks), f"block {idx} out of range (have {len(blocks)})"
    blk = blocks[idx]
    text = narrate.to_speech(blk["text"], blk["kind"], 0)   # never "" — see to_speech
    # Bump on every change to what `idx` means: replies joined the list at wb3,
    # tool calls at wb4. A stale entry would serve the wrong block's audio.
    key = hashlib.md5(
        f"wb4|{sid}|{idx}|{blk['kind']}|{voice}|{rate}|{len(text)}".encode()).hexdigest()
    mp3 = os.path.join(CACHE, key + ".mp3")
    tim = os.path.join(CACHE, key + ".json")
    with LOCK:
        klock = SYNTH_LOCKS.setdefault(key, threading.Lock())
    with klock:
        return _synth_locked(text, voice, rate, mp3, tim)


def _synth_locked(text, voice, rate, mp3, tim):
    """Synthesize under the per-key lock; concurrent requests for the same
    block wait here and then hit the cache instead of racing on the file."""
    if not (os.path.exists(mp3) and os.path.getsize(mp3) > 0 and os.path.exists(tim)):
        assert HAVE_EDGE, "edge-tts is not installed (py -m pip install edge-tts)"
        r = f"{'+' if rate >= 0 else ''}{rate}%"
        words = []
        async def go():
            com = edge_tts.Communicate(text, voice, rate=r,
                                       boundary="WordBoundary")
            with open(mp3, "wb") as f:
                async for ch in com.stream():
                    if ch["type"] == "audio":
                        f.write(ch["data"])
                    elif ch["type"] == "WordBoundary":
                        words.append({"t": round(ch["offset"] / 1e7, 3),
                                      "w": ch["text"]})
        asyncio.run(go())
        assert os.path.getsize(mp3) > 0, "edge-tts produced empty audio"
        with open(tim, "w", encoding="utf-8") as f:
            json.dump(words, f)
    return mp3, tim


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a):
        pass

    def send_json(self, obj, code=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, fp, ctype):
        with open(fp, "rb") as f:
            data = f.read()
        total = len(data)
        rng = self.headers.get("Range", "")
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if m and (m.group(1) or m.group(2)):
            start = int(m.group(1) or 0)
            end = min(int(m.group(2) or total - 1), total - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
            data = data[start:end + 1]
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/":
                self.send_file(os.path.join(HERE, "index.html"),
                               "text/html; charset=utf-8")
            elif u.path == "/api/sessions":
                self.send_json(scan_sessions())
            elif u.path == "/api/version":
                # Lets a long-lived pane notice that index.html changed under
                # it. The player is left open for hours inside the app shell,
                # so without this every shipped change needs a manual reload.
                st = os.stat(os.path.join(HERE, "index.html"))
                self.send_json({"build": f"{int(st.st_mtime)}-{st.st_size}"})
            elif u.path == "/api/blocks":
                path = ID2PATH.get(q.get("session", ""))
                if path is None:
                    scan_sessions()
                    path = ID2PATH.get(q.get("session", ""))
                if path is None:
                    self.send_json({"error": "unknown session"}, 404)
                    return
                after = int(q.get("after", 0))
                self.send_json(get_blocks(path)[after:])
            elif u.path == "/api/audio":
                mp3, _ = synth(q["session"], int(q["idx"]),
                               q.get("voice", DEFAULT_VOICE),
                               int(q.get("rate", 10)))
                self.send_file(mp3, "audio/mpeg")
            elif u.path == "/api/timings":
                _, tim = synth(q["session"], int(q["idx"]),
                               q.get("voice", DEFAULT_VOICE),
                               int(q.get("rate", 10)))
                self.send_file(tim, "application/json; charset=utf-8")
            else:
                self.send_json({"error": "not found"}, 404)
        except Exception as e:
            try:
                self.send_json({"error": str(e)}, 500)
            except Exception:
                pass


def main():
    global ARGS
    ap = argparse.ArgumentParser(description="Web player for Claude Code thinking.")
    ap.add_argument("--root", default=narrate.PROJECTS_ROOT)
    ap.add_argument("--port", type=int, default=8917)
    ap.add_argument("--limit", type=int, default=20, help="sessions listed")
    ap.add_argument("--include-agents", action="store_true")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--panel", action="store_true",
                    help="open the compact sidecar layout, for docking beside "
                         "a terminal (equivalent to visiting /?panel=1)")
    ap.add_argument("--cache-mb", type=int, default=200,
                    help="MP3 cache cap in MB, oldest evicted (default 200)")
    ARGS = ap.parse_args()

    os.makedirs(CACHE, exist_ok=True)
    url = f"http://127.0.0.1:{ARGS.port}" + ("/?panel=1" if ARGS.panel else "")
    # Windows: SO_REUSEADDR (set by http.server) lets a second bind succeed on
    # a live port, so OSError never fires — probe with a connect instead.
    with socket.socket() as probe:
        probe.settimeout(0.5)
        in_use = probe.connect_ex(("127.0.0.1", ARGS.port)) == 0
    if in_use:
        print(f"[server] port {ARGS.port} already in use — opening the page "
              "in your browser instead", flush=True)
        if not ARGS.no_browser:
            webbrowser.open(url)
        return
    ThreadingHTTPServer.allow_reuse_address = False
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler)
    except OSError:
        print(f"[server] could not bind port {ARGS.port}", flush=True)
        if not ARGS.no_browser:
            webbrowser.open(url)
        return
    print(f"[server] {url}  (root: {ARGS.root})", flush=True)
    threading.Thread(target=warm_counts, daemon=True).start()
    threading.Thread(target=prune_cache, daemon=True).start()
    if not ARGS.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] stopped")


if __name__ == "__main__":
    main()
