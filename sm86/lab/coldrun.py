"""Start serve with an ab.py experiment arm, run coldbench.py against it, stop it.

    python coldrun.py LABEL EXP.json:ARM [coldbench args...]
"""
import json
import subprocess
import sys
from pathlib import Path

import ab


def main():
    label, spec, rest = sys.argv[1], sys.argv[2], sys.argv[3:]
    f, _, name = spec.rpartition(":")
    arm = [x for x in json.loads(Path(f).read_text(encoding="utf-8"))["arms"] if x["name"] == name][0]
    cfg, log = ab.arm_config("cold-" + label, arm, 0)
    ab.stop_server()
    console = ab.RUNS / "cold" / f"{label}.console.log"
    console.parent.mkdir(parents=True, exist_ok=True)
    ab.start_server(cfg, arm.get("env", {}), console)
    try:
        r = subprocess.run([str(ab.PY), str(ab.LAB / "coldbench.py"), label, "--url", f"http://127.0.0.1:{ab.PORT}"] + rest)
        print("coldbench exit", r.returncode, flush=True)
    finally:
        ab.stop_server()
    subprocess.run([str(ab.PY), str(ab.LAB / "coldbench.py"), "--summary", label])


if __name__ == "__main__":
    main()
