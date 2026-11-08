"""Cold-prompt prefill bench: fresh prompts of ~4K/16K/32K/64K tokens (a unique first line, so nothing is reused),
real code text from the Strata source tree, 8 generated tokens, temperature 0.  Reads the server's own timings.

    python coldbench.py LABEL [--sizes 4096,16384,32768,65536] [--reps 3] [--url http://127.0.0.1:19100]
    python coldbench.py --summary LABEL [LABEL2 ...]

Writes runs/cold/LABEL.jsonl (one line per request: size, prompt_n, cache_n, prompt_ms, tok/s).
"""
import argparse
import json
import os
import statistics
import time
import urllib.request
import uuid
from pathlib import Path

LAB = Path(__file__).resolve().parent
SRC = Path(os.environ.get("STRATA_DIR") or LAB.parents[1]) / "src"   # the Strata checkout's sources
CHARS_PER_TOKEN = 3.2   # measured roughly on this tokenizer for C++ source; prompt_n in the result is the real count


def corpus() -> str:
    parts = []
    for p in sorted(SRC.rglob("*.cpp")) + sorted(SRC.rglob("*.cu")):
        try:
            parts.append(f"// file: {p.relative_to(SRC)}\n" + p.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
        if sum(len(x) for x in parts) > 400_000:
            break
    return "\n".join(parts)


def post(url: str, body: dict, timeout=1800) -> dict:
    req = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def run(a):
    text = corpus()
    out = LAB / "runs" / "cold" / f"{a.label}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    sizes = [int(x) for x in a.sizes.split(",")]
    with open(out, "a", encoding="utf-8") as f:
        for rep in range(a.reps):
            for size in (sizes if rep % 2 == 0 else list(reversed(sizes))):
                n_chars = int(size * CHARS_PER_TOKEN)
                off = (rep * 7919) % max(1, len(text) - n_chars)
                body = {"messages": [{"role": "user", "content": f"Request {uuid.uuid4()}.\n" + text[off:off + n_chars] +
                                      "\n\nIn one sentence, what does this code do?"}],
                        "max_tokens": 8, "temperature": 0, "chat_template_kwargs": {"enable_thinking": False}}
                t0 = time.time()
                r = post(a.url, body)
                wall = time.time() - t0
                t = r.get("timings") or {}
                rec = {"label": a.label, "rep": rep, "size": size, "prompt_n": t.get("prompt_n"), "cache_n": t.get("cache_n"),
                       "prompt_ms": t.get("prompt_ms"), "prompt_tps": t.get("prompt_per_second"), "wall_s": round(wall, 2)}
                f.write(json.dumps(rec) + "\n")
                f.flush()
                print(json.dumps(rec), flush=True)
                time.sleep(a.gap)


def summary(labels):
    for lab in labels:
        rows = [json.loads(x) for x in open(LAB / "runs" / "cold" / f"{lab}.jsonl", encoding="utf-8")]
        print(f"== {lab}")
        for size in sorted({r["size"] for r in rows}):
            rs = [r for r in rows if r["size"] == size and r.get("prompt_ms")]
            if not rs:
                continue
            ms = statistics.median(r["prompt_ms"] for r in rs)
            n = statistics.median(r["prompt_n"] for r in rs)
            print(f"  ~{size:>6} tok: prompt_n {n:.0f}  median {ms:.0f} ms  {1000 * n / ms:.0f} tok/s  (n={len(rs)}, cache_n {[r['cache_n'] for r in rs]})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("label", nargs="*")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--sizes", default="4096,16384,32768,65536")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--gap", type=float, default=3.0)
    ap.add_argument("--url", default="http://127.0.0.1:19100")
    a = ap.parse_args()
    if a.summary:
        summary(a.label)
    else:
        a.label = a.label[0]
        run(a)
