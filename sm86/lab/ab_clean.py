"""ab.py's paired-turn statistics without the turns another GPU program overlapped.

This machine is shared: other sessions start GPU programs during an A/B, and a contended arm-round reads slower.  Log
the GPU's compute programs every 20 s beside the A/B, one line a sample, the time first (epoch seconds or HH:MM:SS):

    while true; do echo "$(date +%s) $(nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader | tr '\\n' ';')" \\
        >> runs/ab/NAME-gpuapps.log; sleep 20; done

then

    python ab_clean.py runs/ab/NAME.json runs/ab/NAME-gpuapps.log [--engine strata.exe] [--margin 20]

A sample is contended when it lists a program whose path does not end in --engine.  An idle program that only holds a
GPU context (an editor in the background) then contends all the time; to count only programs that use the SMs,
log nvidia-smi pmon instead, every 10 s:

    while true; do echo "$(date +%s) $(nvidia-smi pmon -c 1 -s u | awk '!/^#/ {print $2","$4","$NF}' | tr '\\n' ';')" \\
        >> runs/ab/NAME-pmon.log; sleep 10; done

and pass --pmon N: a pmon sample (pid,sm,name) is contended when a program other than --engine used >= N% of the
SMs.  A turn is contended when a contended sample falls within --margin seconds of it.  Pairs are ab.py's (the same request file in the same round, both
timed with >= 64 tokens); a pair counts as clean when neither turn is contended.  Prints every arm against the first,
and each arm against the one before it, over all pairs and over clean pairs only.
"""
import argparse
import datetime
import json
import math
import random
import re
from pathlib import Path

LAB = Path(__file__).resolve().parent


def other(entry: str, engine: str, pmon) -> bool:
    """True when this sample entry is another program contending for the GPU."""
    if pmon is None:                                   # --query-compute-apps: "pid, path"
        return not entry.split(",", 1)[-1].strip().lower().endswith(engine.lower())
    f = [x.strip() for x in entry.split(",", 2)]       # pmon: "pid,sm,name"; sm is "-" when idle
    return len(f) == 3 and not f[2].lower().endswith(engine.lower()) and f[1].isdigit() and int(f[1]) >= pmon


def samples(log: Path, engine: str, day0: datetime.date, pmon=None) -> list:
    out, cur, prev = [], None, None
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^(\d{9,11}(?:\.\d+)?|\d\d:\d\d:\d\d)\s?(.*)$", line)
        if m:
            stamp, rest = m.group(1), m.group(2)
            if ":" in stamp:
                t = datetime.datetime.combine(day0, datetime.time.fromisoformat(stamp)).timestamp()
                while prev is not None and t < prev - 43200:   # past midnight
                    t += 86400
            else:
                t = float(stamp)
            cur = prev = t
        else:
            rest = line
        if cur is not None and any(other(p, engine, pmon) for p in rest.split(";") if p.strip()):
            out.append(cur)
    return sorted(set(out))


def turns(label: str, busy: list, margin: float) -> dict:
    out = {}
    for line in (LAB / "runs" / "replay" / f"{label}.jsonl").read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        t = d.get("timings") or {}
        if (t.get("predicted_n") or 0) >= 64 and t.get("predicted_per_second"):
            hit = any(d["t"] - margin <= s <= d["t"] + d["wall_s"] + margin for s in busy)
            out[d["file"]] = (t["predicted_per_second"], hit)
    return out


def stats(pr: list) -> str:
    if not pr:
        return "n   0"
    logs = [math.log(x) for x in pr]
    boots = sorted(math.exp(sum(random.choice(logs) for _ in logs) / len(logs)) for _ in range(4000))
    return (f"n {len(pr):3d}  median {sorted(pr)[len(pr) // 2]:.3f}  geo-mean {math.exp(sum(logs) / len(logs)):.3f} "
            f"[95% {boots[100]:.3f}-{boots[3899]:.3f}]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("gpuapps")
    ap.add_argument("--engine", default="strata.exe")
    ap.add_argument("--margin", type=float, default=20.0)
    ap.add_argument("--pmon", type=int, default=None, help="the log is nvidia-smi pmon: contended at >= N%% SM")
    a = ap.parse_args()
    random.seed(7)
    data = json.load(open(a.results, encoding="utf-8"))
    arms = [x["name"] for x in data["experiment"]["arms"]]
    by = {(r["round"], r["arm"]): r["label"] for r in data["results"] if r.get("label")}
    rounds = sorted({k for k, _ in by})
    first = json.loads((LAB / "runs" / "replay" / f"{by[min(by)]}.jsonl").read_text(encoding="utf-8").splitlines()[0])
    busy = samples(Path(a.gpuapps), a.engine, datetime.date.fromtimestamp(first["t"]), a.pmon)
    T = {k: turns(v, busy, a.margin) for k, v in by.items()}
    print(f"{len(busy)} contended samples in {a.gpuapps}")
    for arm in arms:
        print(f"  {arm:16s} contended turns by round {[sum(h for _, h in T[(r, arm)].values()) for r in rounds if (r, arm) in T]}"
              f" of {[len(T[(r, arm)]) for r in rounds if (r, arm) in T]}")
    pairs = [(c, arms[0]) for c in arms[1:]] + [(arms[i], arms[i - 1]) for i in range(2, len(arms))]
    for cand, base in pairs:
        allp, clean = [], []
        for r in rounds:
            if (r, cand) not in T or (r, base) not in T:
                continue
            b, c = T[(r, base)], T[(r, cand)]
            for k in sorted(b.keys() & c.keys()):
                allp.append(c[k][0] / b[k][0])
                if not b[k][1] and not c[k][1]:
                    clean.append(c[k][0] / b[k][0])
        print(f"{cand} vs {base}\n  all pairs    {stats(allp)}\n  clean pairs  {stats(clean)}")


if __name__ == "__main__":
    main()
