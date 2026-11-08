"""Write a tools/force_check.py CFG (Windows) from the "engine started:" line of an engine log, so the check runs the
engine with exactly the arguments the server gave it.

    python fc_config.py <engine.log> <out.json> [--env K=V ...] [--drop FLAG ...] [--set FLAG VALUE ...]

force_check starts `exe --serve <args>` itself; on Windows the CUDA DLLs come from PATH (the server's lib_dirs), which
force_check's own lib_dirs handling (LD_LIBRARY_PATH) does not set, so PATH goes into the CFG's env. The expert profile
is copied fresh per engine start (profile_src), as force_check does for every arm.
"""
import argparse
import json
import os
from pathlib import Path

BASE = Path(r"C:\src\Strata\strata-iq3_xxs.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("out")
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--drop", action="append", default=[])
    ap.add_argument("--set", nargs=2, action="append", default=[])
    a = ap.parse_args()
    lines = [x for x in open(a.log, encoding="utf-8", errors="replace") if "engine started:" in x]
    if not lines:
        raise SystemExit(f"no 'engine started:' line in {a.log}")
    toks = lines[-1].split("engine started:", 1)[1].split()
    exe, args = toks[0], [t for t in toks[1:] if t != "--serve"]
    for flag in a.drop:
        if flag in args:
            i = args.index(flag)
            two = i + 1 < len(args) and not args[i + 1].startswith("--")
            del args[i:i + (2 if two else 1)]
    for flag, val in a.set:
        if flag in args:
            args[args.index(flag) + 1] = val
        else:
            args += [flag, val]
    base = json.load(open(BASE, encoding="utf-8"))
    path = os.pathsep.join([str(Path(exe).parent), *base.get("lib_dirs", []), os.environ.get("PATH", "")])
    env = {"PATH": path}
    for kv in a.env:
        k, _, v = kv.partition("=")
        env[k] = v
    cfg = {"exe": exe, "args": args, "cwd": base.get("cwd", r"C:\src\Strata"), "env": env}
    if "--expert-profile" in args:
        cfg["profile_src"] = args[args.index("--expert-profile") + 1]
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(cfg, open(a.out, "w", encoding="utf-8"), indent=1)
    print(f"{a.out}: {exe} {' '.join(args)}")


if __name__ == "__main__":
    main()
