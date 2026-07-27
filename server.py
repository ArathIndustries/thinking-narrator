#!/usr/bin/env python3
"""Web UI for the thinking narrator.

Serves a localhost player page: session list, scrollable thought log, and a
native browser audio player — which is what provides pause, scrubbing
(rewind), volume, and speed controls. The server tails transcripts, extracts
thinking blocks, and synthesizes per-block MP3s (edge-tts, cached in %TEMP%).

Run: py server.py    → opens http://127.0.0.1:8917 in the default browser.

Endpoints:
  GET /                      player page
  GET /api/sessions          recent sessions, newest first
  GET /api/blocks?session=&after=   thinking blocks (idx, ts, text)
  GET /api/audio?session=&idx=&voice=&rate=   MP3 for one block (Range OK)
"""

import argparse
import asyncio
import glob
import hashlib
import json
import os
import re
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
            out.append({"id": sid, "title": TITLES[p],
                        "project": os.path.basename(os.path.dirname(p)),
                        "mtime": int(os.path.getmtime(p))})
    return out


def get_blocks(path):
    with LOCK:
        st = STORE.get(path)
        if st is None:
            st = STORE[path] = {"tail": narrate.Tail(path, True), "blocks": []}
        for rec in st["tail"].read_new():
            for t in narrate.extract_thinking(rec, ARGS.include_agents):
                st["blocks"].append({"idx": len(st["blocks"]),
                                     "ts": rec.get("timestamp", ""), "text": t})
        return list(st["blocks"])


def get_audio(sid, idx, voice, rate):
    path = ID2PATH.get(sid)
    if path is None:
        scan_sessions()
        path = ID2PATH.get(sid)
    assert path, f"unknown session {sid!r}"
    blocks = get_blocks(path)
    assert 0 <= idx < len(blocks), f"block {idx} out of range (have {len(blocks)})"
    text = narrate.clean(blocks[idx]["text"], 0)
    key = hashlib.md5(f"{sid}|{idx}|{voice}|{rate}|{len(text)}".encode()).hexdigest()
    mp3 = os.path.join(CACHE, key + ".mp3")
    if not (os.path.exists(mp3) and os.path.getsize(mp3) > 0):
        assert HAVE_EDGE, "edge-tts is not installed (py -m pip install edge-tts)"
        r = f"{'+' if rate >= 0 else ''}{rate}%"
        async def go():
            await edge_tts.Communicate(text, voice, rate=r).save(mp3)
        asyncio.run(go())
        assert os.path.getsize(mp3) > 0, "edge-tts produced empty audio"
    return mp3


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
                mp3 = get_audio(q["session"], int(q["idx"]),
                                q.get("voice", DEFAULT_VOICE),
                                int(q.get("rate", 10)))
                self.send_file(mp3, "audio/mpeg")
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
    ARGS = ap.parse_args()

    os.makedirs(CACHE, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", ARGS.port), Handler)
    url = f"http://127.0.0.1:{ARGS.port}"
    print(f"[server] {url}  (root: {ARGS.root})", flush=True)
    if not ARGS.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] stopped")


if __name__ == "__main__":
    main()
