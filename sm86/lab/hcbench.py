"""Hyper-connection read: bit identity and cold-weight time per variant, with Strata's own fused_gr_bench.

Runs build-sm86\\fused_gr_bench.exe once per arm (an arm = ';'-separated ENV=V settings, "" = the default) and compares
every arm's output hashes per (T, apply, inject) cell with the first arm's: identical hashes = the same bits on every
output (lo, rs, inject, mixed, R).  Prints the cold read time and the norm/down/up stamps per T.

    python hcbench.py NAME "" "STRATA_GR_DOWN_NW=4" "STRATA_GR_UP_WIDE=1" [--iters 300] [--tmax 8] [--cold 40]
Writes runs/hc/NAME.json.
"""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

LAB = Path(__file__).resolve().parent
STRATA = Path(os.environ.get("STRATA_DIR") or LAB.parents[1])   # the Strata checkout; this lab sits in its sm86/lab
EXE = STRATA / "build-sm86" / "fused_gr_bench.exe"
LIBS = [str(STRATA / "engine"), str(STRATA / ".venv" / "Lib" / "site-packages" / "nvidia" / "cu13" / "bin" / "x86_64")]
RE_HASH = re.compile(r"T (\d+) apply (\d+) inject (\d+) \|.*\| hash ([0-9a-f]+)")
RE_COLD = re.compile(r"COLD\((\d+) sets\) fast (\d+) T (\d+) \| read\s+([\d.]+) us.*norm\s+([\d.]+) down\s+([\d.]+) up\s+([\d.]+)")


def run(arm, a):
    env = {k: v for k, v in os.environ.items() if not k.startswith("STRATA_")}
    env["PATH"] = os.pathsep.join(LIBS + [env.get("PATH", "")])
    env["STRATA_HC_SPLIT"] = "2"   # the bench never runs fused_gr_check: without this it times the plain read, not the engine's staged one
    for part in [p for p in arm.split(";") if p.strip()]:
        k, _, v = part.strip().partition("=")
        env[k] = v
    r = subprocess.run([str(EXE), str(a.iters), "1", str(a.tmax), str(a.cold)], capture_output=True, text=True, env=env, timeout=1800)
    out = r.stdout + r.stderr
    hashes = {f"{m[0]}/{m[1]}/{m[2]}": m[3] for m in RE_HASH.findall(out)}
    cold = {}
    for m in RE_COLD.findall(out):
        if m[1] == "0":   # fast 0 = the bf16 read the engine runs on CUDA (fast 1 is the AMD path's switch, 2 the Q8 read)
            cold.setdefault(m[2], []).append({"read": float(m[3]), "norm": float(m[4]), "down": float(m[5]), "up": float(m[6])})
    persist = {m[1]: float(m[2]) for m in re.findall(r"COLD\((\d+) sets\) persist T (\d+) \| read\s+([\d.]+) us", out)}
    bw = [{"v": int(m[0]), "bytes": int(m[1]), "us": float(m[2]), "gbs": float(m[3])}
          for m in re.findall(r"BW probe v (\d+) \| (\d+) bytes cold \|\s+([\d.]+) us a read \(events\) \|\s+(\d+) GB/s", out)]
    res = [{"T": int(m[0]), "hold": int(m[1]), "us": float(m[2]), "status": m[3]}
           for m in re.findall(r"RES probe T (\d+) hold (\d+) \|\s+([\d.]+) us a read \(events\) \| (\S+)", out)]
    prof = re.findall(r"(RES prof T \d+ \|.*)", out)
    return {"arm": arm, "rc": r.returncode, "hashes": hashes, "cold": cold, "persist": persist, "bw": bw, "res": res, "prof": prof, "tail": out[-1500:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("arms", nargs="+")
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--tmax", type=int, default=8)
    ap.add_argument("--cold", type=int, default=40)
    a = ap.parse_args()
    res = []
    for arm in a.arms:
        print("running", arm or "(default)", flush=True)
        res.append(run(arm, a))
    base = res[0]
    print(f"{'arm':34s} {'T':>2s} {'read':>7s} {'norm':>6s} {'down':>6s} {'up':>6s}   bits vs default")
    for r in res:
        same = r["hashes"] == base["hashes"] and bool(r["hashes"])
        diff = sorted(k for k in base["hashes"] if r["hashes"].get(k) != base["hashes"][k])
        tag = "IDENTICAL" if same else f"DIFFERENT ({len(diff)} of {len(base['hashes'])} cells, rc {r['rc']})"
        for t, rows in sorted(r["cold"].items(), key=lambda x: int(x[0])):
            x = rows[-1]
            print(f"{(r['arm'] or '(default)')[-34:]:34s} {t:>2s} {x['read']:7.1f} {x['norm']:6.1f} {x['down']:6.1f} {x['up']:6.1f}   {tag}")
        if r.get("persist"):
            print(f"{(r['arm'] or '(default)')[-34:]:34s} persist read us by T: " + " ".join(f"{t}:{v:.1f}" for t, v in sorted(r["persist"].items(), key=lambda x: int(x[0]))))
        for b in r.get("bw", []):
            print(f"{(r['arm'] or '(default)')[-34:]:34s} BW probe v {b['v']}: {b['bytes']} B {b['us']:.1f} us {b['gbs']:.0f} GB/s")
        for b in r.get("res", []):
            print(f"{(r['arm'] or '(default)')[-34:]:34s} RES probe T {b['T']} hold {b['hold']}: {b['us']:.1f} us {b['status']}")
        for line in r.get("prof", []):
            print(f"{(r['arm'] or '(default)')[-34:]:34s} {line}")
        if not r["cold"]:
            print(f"{(r['arm'] or '(default)')[-34:]:34s} no COLD lines   {tag}\n{r['tail']}")
    out = LAB / "runs" / "hc" / f"{a.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main()
