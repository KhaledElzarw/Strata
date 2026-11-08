"""Nsight Systems timeline of serve decode on replayed real turns (the tuned live arm), for the GPU idle gaps per window.

    python nsyscap.py NAME [--arm EXP.json:ARM] [--exe <checkout>/build-sm86/strata.exe] [--env K=V ...] [--limit 3]
                      [--graph node|graph]

--arm takes the arm (exe, drafting, args, env) from an ab.py experiment file instead of the built-in tuned arm;
--env then adds to or overrides its environment.

Starts serve under `nsys launch` (child processes traced), waits for /health loaded, warms up (2 requests), then records
only the replay of --limit turns from runs/replayset/hermes-v1 (nsys start / stop).  Writes runs/nsys/NAME.nsys-rep and
the kernel / API summaries (runs/nsys/NAME_*.csv).  The server is stopped at the end.
"""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import ab
import replay

NSYS = r"C:\Program Files\NVIDIA Corporation\Nsight Systems 2025.3.2\target-windows-x64\nsys.exe"
TUNED = {"name": "tuned", "drafting": "dflash2", "user_args": ["--draft-conf", "0.65"],
         "set": {"--conversation-cache-mib": "2048", "--expert-cache": "7100"},
         "env": {"STRATA_DRAFT_PACK": str(ab.STRATA / "dflash2" / "qwen3.8-flash-next-dflash2.strata1.q4_0-selq4.pack")}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--exe")
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--graph", default="node", choices=["node", "graph"])
    ap.add_argument("--arm", help="EXP.json:ARM, an ab.py experiment's arm")
    a = ap.parse_args()
    arm = dict(TUNED, env=dict(TUNED["env"]))
    if a.arm:
        f, _, name = a.arm.rpartition(":")
        arms = [x for x in json.loads(Path(f).read_text(encoding="utf-8"))["arms"] if x["name"] == name]
        if len(arms) != 1:
            raise SystemExit(f"no arm {name!r} in {f}")
        arm = dict(arms[0], env=dict(arms[0].get("env", {})))
    if a.exe:
        arm["exe"] = a.exe
    for kv in a.env:
        k, _, v = kv.partition("=")
        arm["env"][k] = v
    cfg, log = ab.arm_config("nsys-" + a.name, arm, 1)
    out = ab.RUNS / "nsys"
    out.mkdir(parents=True, exist_ok=True)
    rep = out / f"{a.name}.nsys-rep"
    sess = "strata_" + a.name
    ab.stop_server()
    env = dict(os.environ, PYTHONUNBUFFERED="1", **arm["env"])
    console = out / f"{a.name}.console.log"
    p = subprocess.Popen([NSYS, "launch", f"--session-new={sess}", "--trace=cuda,nvtx",
                          f"--cuda-graph-trace={a.graph}", str(ab.PY), str(ab.STRATA / "serve" / "server.py"),
                          "--engine", "strata", "--config", str(cfg), "--port", str(ab.PORT)],
                         cwd=str(ab.STRATA), env=env, stdout=open(console, "wb"), stderr=subprocess.STDOUT)
    t0 = time.time()
    while not ab.health().get("loaded"):
        if p.poll() is not None or time.time() - t0 > 900:
            raise SystemExit(f"server did not load (see {console})")
        time.sleep(1)
    print(f"loaded in {time.time() - t0:.0f} s", flush=True)
    for _ in range(2):
        ab.warmup()
    r = subprocess.run([NSYS, "start", f"--session={sess}", "-o", str(rep.with_suffix("")), "--force-overwrite=true"],
                       capture_output=True, text=True)
    print("start:", r.returncode, (r.stdout + r.stderr).strip()[-300:], flush=True)
    x = ab.Args()
    x.src, x.label, x.url = str(ab.LAB / "runs/replayset/hermes-v1"), f"nsys-{a.name}", f"http://127.0.0.1:{ab.PORT}"
    x.temperature, x.max_tokens, x.limit, x.repeat, x.timeout, x.gap, x.extra = None, None, a.limit, 1, 600, 1.0, '{"seed": 1234}'
    rp = ab.RUNS / "replay" / f"{x.label}.jsonl"
    if rp.exists():
        rp.unlink()
    replay.run(x)
    r = subprocess.run([NSYS, "stop", f"--session={sess}"], capture_output=True, text=True)
    print("stop:", r.returncode, (r.stdout + r.stderr).strip()[-300:], flush=True)
    subprocess.run([NSYS, "shutdown", f"--session={sess}"], capture_output=True, text=True)
    ab.stop_server()
    print(replay.stats(replay.load(x.label), 64), flush=True)
    if rep.exists():
        r = subprocess.run([NSYS, "stats", "--force-export=true", "--report", "cuda_gpu_kern_sum,cuda_api_sum,cuda_gpu_trace",
                            "--format", "csv", "-o", str(out / a.name), str(rep)], capture_output=True, text=True)
        print("stats:", r.returncode, (r.stdout + r.stderr).strip()[-500:], flush=True)
    else:
        print("no report written", flush=True)


if __name__ == "__main__":
    main()
