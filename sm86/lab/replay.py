"""Replay recorded chat requests against Strata, summarize decode speed, and check exactness.

  python replay.py run --src runs/requests/<tag> --label <label> [--url http://127.0.0.1:19100]
                       [--temperature 0] [--max-tokens 1024] [--limit N] [--repeat 1] [--extra '{"spec_min_p": 0.7}']
                       [--gap 2] [--gpu-gate 5] [--gpu-wait 1800]
  python replay.py summary <label | turns:<tag>> ...
  python replay.py diff <ref_label> <label>

Results go to runs/replay/<label>.jsonl. Decode speed is Strata's own `predicted_per_second` (every kept token over
first-to-last token time; prompt reading excluded). Turns with fewer than --min-tokens generated tokens are left out of
the speed statistics (too short to time) but still count for exactness.

--gpu-gate N: the machine is shared, so before each request wait until no other program has used >= N% of the GPU's
SMs for 30 s (checks of two one-second nvidia-smi pmon samples), at most --gpu-wait seconds a request; the wait is
recorded as gpu_wait_s.
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RUNS = Path(__file__).with_name("runs")


def post(url: str, body: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def answer_text(r: dict) -> str:
    """The generated content in a form two runs can be compared by: text, reasoning, tool calls (name + arguments;
    the call ids are random per run)."""
    msg = ((r.get("choices") or [{}])[0].get("message") or {})
    calls = [((c.get("function") or {}).get("name"), (c.get("function") or {}).get("arguments"))
             for c in msg.get("tool_calls") or []]
    return json.dumps({"c": msg.get("content"), "r": msg.get("reasoning_content"), "t": calls}, ensure_ascii=False)


def gpu_others(engine: str = "strata.exe", samples: int = 2) -> list:
    """Other programs' SM use in `samples` one-second nvidia-smi pmon samples: [(name, sm%)]; [] when pmon fails."""
    try:
        out = subprocess.run(["nvidia-smi", "pmon", "-c", str(samples), "-s", "u"], capture_output=True, text=True,
                             timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    busy = []
    for line in out.splitlines():
        f = line.split()     # gpu pid type sm mem enc dec jpg ofa command; sm is "-" when the program is idle
        if len(f) >= 4 and not line.startswith("#") and f[3].isdigit() and not f[-1].lower().endswith(engine.lower()):
            busy.append((f[-1], int(f[3])))
    return busy


_last_busy = 0.0   # when a check last saw another program on the SMs, kept across a run's requests


def wait_gpu_free(min_sm: int, max_wait: float, label: str, quiet: float = 30.0) -> float:
    """Wait until no other program has used >= min_sm% of the SMs for `quiet` seconds (a game idles a few seconds
    between bursts), at most max_wait seconds; returns the seconds spent, the checks included."""
    global _last_busy
    t0, said = time.time(), False
    while True:
        busy = sorted({n for n, s in gpu_others() if s >= min_sm})
        now = time.time()
        if busy:
            _last_busy = now
        elif now - _last_busy >= quiet:
            return now - t0
        if now - t0 >= max_wait:
            print(f"{label}: the GPU is still busy after {max_wait:.0f} s ({', '.join(busy) or 'recently'}), going on",
                  flush=True)
            return now - t0
        if not said:
            print(f"{label}: waiting for the GPU ({', '.join(busy) or 'busy in the last %.0f s' % quiet})", flush=True)
            said = True
        time.sleep(5)


def run(a):
    files = sorted(Path(a.src).glob("*.json"))[: a.limit or None]
    if not files:
        sys.exit(f"no request files in {a.src}")
    out = RUNS / "replay" / f"{a.label}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    extra = json.loads(a.extra) if a.extra else {}
    fails = 0
    with open(out, "a", encoding="utf-8") as f:
        for rep in range(a.repeat):
            for i, p in enumerate(files):
                if (RUNS / "THERMAL_STOP").exists():
                    sys.exit("THERMAL_STOP present: aborting (see runs/THERMAL_STOP)")
                if fails >= 3:                  # a server that stopped answering: no point waiting out every request
                    print(f"{a.label}: 3 requests in a row failed, stopping this run", flush=True)
                    return
                body = json.loads(p.read_text(encoding="utf-8"))
                body["stream"] = False
                body.pop("stream_options", None)
                if a.temperature is not None:
                    body["temperature"] = a.temperature
                if a.max_tokens:
                    cur = body.pop("max_completion_tokens", None) or body.get("max_tokens")
                    body["max_tokens"] = min(a.max_tokens, cur) if cur else a.max_tokens
                body.update(extra)
                waited = wait_gpu_free(a.gpu_gate, a.gpu_wait, a.label) if getattr(a, "gpu_gate", 0) else None
                if getattr(a, "gap", 0) and (rep or i):    # idle seconds before each request but the first (tool time)
                    time.sleep(max(0.0, a.gap - (waited or 0.0)))
                t0 = time.time()
                try:
                    r, err = post(a.url.rstrip("/") + "/v1/chat/completions", body, a.timeout), None
                except Exception as e:  # noqa: BLE001 - a failed turn is recorded, not fatal
                    r, err = {}, f"{type(e).__name__}: {e}"
                fails = fails + 1 if err else 0
                text = answer_text(r) if r else ""
                tm = r.get("timings") or {}
                rec = {"label": a.label, "file": p.name, "i": i, "rep": rep, "t": round(t0, 2),
                       "wall_s": round(time.time() - t0, 2), "timings": r.get("timings"), "usage": r.get("usage"),
                       "finish": ((r.get("choices") or [{}])[0].get("finish_reason")),
                       "sha": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], "text": text, "error": err}
                if waited is not None:
                    rec["gpu_wait_s"] = round(waited, 1)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                print(f"{a.label} rep{rep} {i + 1}/{len(files)} {p.name}: "
                      f"{tm.get('predicted_n')} tok @ {tm.get('predicted_per_second')} tok/s, "
                      f"prompt {(tm.get('prompt_n') or 0) + (tm.get('cache_n') or 0)}"
                      + (f" ERROR {err}" if err else ""), flush=True)


def load(label: str) -> list:
    if label.startswith("turns:"):
        tag = label[len("turns:"):]
        with open(RUNS / "turns.jsonl", encoding="utf-8") as f:
            return [r for r in map(json.loads, f) if r.get("tag") == tag]
    with open(RUNS / "replay" / f"{label}.jsonl", encoding="utf-8") as f:
        return [json.loads(x) for x in f]


def pct(xs: list, q: float):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)


def stats(rows: list, min_tokens: int) -> dict:
    tms = [r["timings"] for r in rows if r.get("timings")]
    use = [t for t in tms if (t.get("predicted_n") or 0) >= min_tokens and t.get("predicted_per_second")]
    tok = sum(t["predicted_n"] for t in use)
    ms = sum(t["predicted_ms"] for t in use)
    dn = sum(t.get("draft_n") or 0 for t in use)
    da = sum(t.get("draft_n_accepted") or 0 for t in use)
    prompts = [(t.get("prompt_n") or 0) + (t.get("cache_n") or 0) for t in tms]
    sp = [t["predicted_per_second"] for t in use]
    return {"turns": len(rows), "timed": len(use), "median": pct(sp, 0.5), "p10": pct(sp, 0.1), "p90": pct(sp, 0.9),
            "tok_weighted": round(tok / (ms / 1000), 1) if ms else None,
            "accept": round(da / dn, 3) if dn else None,
            "prompt_median": pct(prompts, 0.5), "prompt_max": max(prompts) if prompts else None,
            "gen_tokens": tok, "errors": sum(1 for r in rows if r.get("error"))}


def summary(a):
    for label in a.labels:
        print(label, json.dumps(stats(load(label), a.min_tokens)))


def diff(a):
    ref = {r["file"]: r for r in load(a.ref) if r.get("rep", 0) == 0 and not r.get("error")}
    cur = {r["file"]: r for r in load(a.label) if r.get("rep", 0) == 0 and not r.get("error")}
    same, differ = 0, 0
    for k in sorted(ref.keys() & cur.keys()):
        x, y = ref[k], cur[k]
        if x["sha"] == y["sha"]:
            same += 1
            continue
        differ += 1
        tx, ty = x.get("text") or "", y.get("text") or ""
        i = next((j for j in range(min(len(tx), len(ty))) if tx[j] != ty[j]), min(len(tx), len(ty)))
        print(f"DIFF {k}: first divergence at char {i} of {len(tx)}/{len(ty)}\n"
              f"   ref: {tx[max(0, i - 60):i + 60]!r}\n   new: {ty[max(0, i - 60):i + 60]!r}")
    print(f"identical {same}/{same + differ} (ref {a.ref}, new {a.label})")
    sys.exit(0 if differ == 0 else 1)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--src", required=True)
    r.add_argument("--label", required=True)
    r.add_argument("--url", default="http://127.0.0.1:19100")
    r.add_argument("--temperature", type=float)
    r.add_argument("--max-tokens", type=int)
    r.add_argument("--limit", type=int)
    r.add_argument("--repeat", type=int, default=1)
    r.add_argument("--extra")
    r.add_argument("--timeout", type=float, default=1800)
    r.add_argument("--gap", type=float, default=0.0, help="idle seconds between requests (an agent's tool time)")
    r.add_argument("--gpu-gate", type=int, default=0, help="wait before each request while another program uses >= N%% SM")
    r.add_argument("--gpu-wait", type=float, default=1800.0, help="at most this many seconds of --gpu-gate wait a request")
    s = sub.add_parser("summary")
    s.add_argument("labels", nargs="+")
    s.add_argument("--min-tokens", type=int, default=64)
    d = sub.add_parser("diff")
    d.add_argument("ref")
    d.add_argument("label")
    a = ap.parse_args()
    {"run": run, "summary": summary, "diff": diff}[a.cmd](a)


if __name__ == "__main__":
    main()
