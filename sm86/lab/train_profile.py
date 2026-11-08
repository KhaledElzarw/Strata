"""Train a workload expert profile: one server start of the tuned config with --expert-profile-save, replay the given
request dirs (lab-relative), wait for the periodic save (every minute, between requests), stop the server.

    python train_profile.py <out.bin> <src dir> [<src dir> ...]

The saved profile ranks the experts the adaptive tier holds in VRAM first, then the rest by the routing counted since
the start; `--expert-profile <out.bin>` starts a server from it.
"""
import hashlib
import sys
import time
from pathlib import Path

import ab

PACK = str(ab.STRATA / "dflash2" / "qwen3.8-flash-next-dflash2.strata1.q4_0-selq4.pack")


def main():
    out = Path(sys.argv[1]).resolve()
    srcs = sys.argv[2:]
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    arm = {"name": "train", "drafting": "dflash2", "user_args": ["--draft-conf", "0.65"],
           "set": {"--conversation-cache-mib": "2048", "--expert-cache": "7000"},
           "add": ["--expert-profile-save", str(out), "--expert-profile-save-every", "1"],
           "env": {"STRATA_DRAFT_PACK": PACK}}
    ab.stop_server()
    cfg, log = ab.arm_config("prof", arm, 0)
    _, load_s = ab.start_server(cfg, arm["env"], log.with_suffix(".console.log"))
    ab.warmup()
    t0, t1 = ab.replay_arm({"src": srcs, "seed": 1234, "timeout": 600}, arm, "prof-train")
    print(f"replayed in {t1 - t0:.0f} s (load {load_s} s); waiting for the periodic save", flush=True)
    time.sleep(70)
    ab.warmup()                      # a request after the minute: the save runs between requests
    for _ in range(60):
        if out.exists() and time.time() - out.stat().st_mtime < 120:
            break
        time.sleep(2)
    time.sleep(5)
    ab.stop_server()
    if not out.exists():
        raise SystemExit(f"no profile written at {out} (see {log})")
    blob = out.read_bytes()
    print(f"profile {out}: {len(blob)} bytes, sha256 {hashlib.sha256(blob).hexdigest()[:16]}, "
          f"saved {time.ctime(out.stat().st_mtime)}")


if __name__ == "__main__":
    main()
