"""Pass-through proxy in front of Strata: logs every model request's engine timings and saves chat request bodies.

    python turnlog.py --listen 19000 --upstream 127.0.0.1:19100 --dir runs

Each request is tagged with the text in <dir>/TAG (read per request), so one proxy serves every experiment.
  <dir>/turns.jsonl            one line per chat request: usage, Strata `timings`, finish reason, wall times
  <dir>/requests/<tag>/*.json  the request bodies, for replay.py
Stdlib only, streams SSE through unbuffered (read1), adds no latency to the engine's own clock.
"""
import argparse
import http.client
import itertools
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
       "transfer-encoding", "upgrade", "host", "content-length"}
CHAT_PATHS = ("/chat/completions", "/completions", "/responses")
LOCK = threading.Lock()
SEQ = itertools.count(1)


class Cfg:
    def __init__(self, a):
        self.host, port = a.upstream.rsplit(":", 1)
        self.port = int(port)
        self.dir = Path(a.dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.timeout = a.timeout

    def tag(self) -> str:
        try:
            return (self.dir / "TAG").read_text(encoding="utf-8").strip() or "untagged"
        except OSError:
            return "untagged"


class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):
        pass

    do_GET = do_POST = do_PUT = do_DELETE = do_OPTIONS = do_HEAD = lambda self: self.forward()

    def read_body(self) -> bytes:
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            data = bytearray()
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip() or b"0", 16)
                if size == 0:
                    while self.rfile.readline() not in (b"\r\n", b"\n", b""):
                        pass
                    return bytes(data)
                data += self.rfile.read(size)
                self.rfile.readline()
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def forward(self):
        cfg: Cfg = self.server.cfg
        body = self.read_body()
        t0 = time.time()
        seq = next(SEQ)
        tag = cfg.tag()
        is_chat = self.command == "POST" and self.path.split("?")[0].rstrip("/").endswith(CHAT_PATHS)
        req = None
        if is_chat:
            try:
                req = json.loads(body)
            except ValueError:
                req = None
            if isinstance(req, dict):
                d = cfg.dir / "requests" / tag
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{int(t0 * 1000)}-{seq:06d}.json").write_bytes(body)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        headers["Host"] = f"{cfg.host}:{cfg.port}"
        if body or self.command in ("POST", "PUT"):
            headers["Content-Length"] = str(len(body))
        up = http.client.HTTPConnection(cfg.host, cfg.port, timeout=cfg.timeout)
        try:
            up.request(self.command, self.path, body=body or None, headers=headers)
            r = up.getresponse()
        except OSError as e:
            self.send_error(502, f"upstream: {e}")
            if is_chat:
                self.log_turn(cfg, tag, seq, req, t0, None, None, None, None, f"upstream: {e}")
            return
        stream = "text/event-stream" in (r.getheader("Content-Type") or "")
        clen = r.getheader("Content-Length")
        chunked = clen is None and self.command != "HEAD"
        self.send_response(r.status, r.reason)
        for k, v in r.getheaders():
            if k.lower() not in HOP:
                self.send_header(k, v)
        if chunked:
            self.send_header("Transfer-Encoding", "chunked")
        elif clen is not None:
            self.send_header("Content-Length", clen)
        self.end_headers()
        first, final, finish, err = None, None, None, None
        tail = b""
        full = bytearray() if is_chat and not stream else None
        try:
            while True:
                chunk = r.read1(65536)
                if not chunk:
                    break
                if first is None:
                    first = time.time()
                self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk) if chunked else chunk)
                self.wfile.flush()
                if is_chat and stream:
                    tail += chunk
                    *lines, tail = tail.split(b"\n")
                    for ln in lines:
                        ln = ln.strip()
                        if not ln.startswith(b"data:") or ln[5:].strip() in (b"", b"[DONE]"):
                            continue
                        try:
                            j = json.loads(ln[5:])
                        except ValueError:
                            continue
                        ch = j.get("choices") or [{}]
                        if ch and ch[0].get("finish_reason"):
                            finish = ch[0]["finish_reason"]
                        if j.get("usage") or j.get("timings"):
                            final = j
                elif full is not None:
                    full += chunk
            if chunked:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
        except OSError as e:
            err = f"stream: {e}"
        finally:
            up.close()
        if full is not None:
            try:
                final = json.loads(bytes(full))
                finish = (final.get("choices") or [{}])[0].get("finish_reason")
            except ValueError:
                pass
        if is_chat:
            self.log_turn(cfg, tag, seq, req, t0, first, r.status, final, finish, err)

    def log_turn(self, cfg, tag, seq, req, t0, first, status, final, finish, err):
        req = req if isinstance(req, dict) else {}
        rec = {"ts": round(t0, 3), "seq": seq, "tag": tag, "path": self.path,
               "client": self.headers.get("User-Agent"), "model": req.get("model"),
               "stream": bool(req.get("stream")), "temperature": req.get("temperature"),
               "max_tokens": req.get("max_tokens") or req.get("max_completion_tokens"),
               "n_messages": len(req.get("messages") or []), "n_tools": len(req.get("tools") or []),
               "status": status, "finish": finish,
               "ttfb_s": round(first - t0, 3) if first else None, "total_s": round(time.time() - t0, 3),
               "usage": (final or {}).get("usage"), "timings": (final or {}).get("timings"), "error": err}
        with LOCK, open(cfg.dir / "turns.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", type=int, default=19000)
    ap.add_argument("--upstream", default="127.0.0.1:19100")
    ap.add_argument("--dir", default=str(Path(__file__).with_name("runs")))
    ap.add_argument("--timeout", type=float, default=3600)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.listen), Proxy)
    srv.daemon_threads = True
    srv.cfg = Cfg(a)
    print(f"turnlog: 127.0.0.1:{a.listen} -> {a.upstream}, logs in {srv.cfg.dir}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
