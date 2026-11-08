"""Write Strata's run config for launch-strata.ps1: the tuned config with the GPU expert cache sized to the VRAM free
right now (an explicit cache is not shrunk by the engine after it is written, so it must fit before the start).

    python make_run_config.py <tuned.json> <out.json> <free_vram_mib> [--draft-conf auto|0.5|0.65 ...]

Measured on this PC (RTX 3090, 2026-11-07): Strata's own use apart from the expert cache is about 6,413 MiB, a cache
step of --expert-cache N costs about 2.222 MiB (7000 -> 15,555 MiB, 9,371 slots), and the server should keep about
1,300 MiB free after loading (below ~900 MiB decode can stall).  So N = (free - 6,413 - 1,300) / 2.222, rounded down to
a hundred, at most 9000; below 2000 Strata's own "auto" sizing is used instead.
The free figure is capped at 23,550 MiB: under WDDM one process gets at most ~23,556 MiB of this 24 GiB card (measured
2026-11-07 with no display on the 3090: NVML read 1,481 MiB free, the engine's cudaMemGetInfo 714, at --expert-cache
7400).  With the desktop on the card (1.27 GB) the card's own free figure is below the cap, so nothing changes there.
DFlash2 confidence (auto): 0.65, the tuned pack's conf.  On this PC 0.5 lost 1.9% at the full cache (e5b, 9,371 slots,
paired geo-mean 0.981, 95% 0.965-0.997), and 0.65 is also Strata's best at ~6,500 slots, the smaller caches.
"""
import argparse
import json
from pathlib import Path

OTHER_MIB, KEEP_FREE_MIB, MIB_PER_N, N_MAX, N_MIN, BUDGET_CAP_MIB = 6413, 1300, 2.222, 9000, 2000, 23550


def cache_for(free_mib: int) -> str:
    n = int((min(free_mib, BUDGET_CAP_MIB) - OTHER_MIB - KEEP_FREE_MIB) / MIB_PER_N) // 100 * 100
    return str(min(n, N_MAX)) if n >= N_MIN else "auto"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tuned")
    ap.add_argument("out")
    ap.add_argument("free_mib", type=int)
    ap.add_argument("--draft-conf", default="auto")
    a = ap.parse_args()
    cfg = json.loads(Path(a.tuned).read_text(encoding="utf-8-sig"))
    args = list(cfg["args"])
    cache = cache_for(a.free_mib)
    if "--expert-cache" in args:
        args[args.index("--expert-cache") + 1] = cache
    else:
        args += ["--expert-cache", cache]
    cfg["args"] = args
    conf = a.draft_conf
    if conf == "auto":
        conf = "0.65"
    cfg["user_args"] = ["--draft-conf", conf]
    cfg["log"] = str(Path(a.out).with_suffix(".log"))
    Path(a.out).write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    print(f"expert cache {cache} (VRAM free {a.free_mib} MiB), draft-conf {conf} -> {a.out}")


if __name__ == "__main__":
    main()
