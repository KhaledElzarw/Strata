"""Bit-identity check between two Strata arms (engine exe, environment, extra engine args) on one fixed forced text.

Each arm scores the same short SET through force_check's decode path (STRATA_FOLLOW forces the continuation through the
real verify windows, drafter included; STRATA_FOLLOW_LOGPOS writes the FP32 head log-probabilities of every row to 9
decimals).  The two TSVs are compared line by line: identical files = the same head logits at every scored position.
A rounding-level change (another summation order) moves the 9th decimal almost everywhere, so it shows at once.

Pinned in both arms, so that only the change under test differs:
  --adapt-every 0      no expert swaps between windows (the adaptive tier would move experts between GPU and CPU)
  --pcie-frac F        no PcieAuto refinement (it splits non-resident experts between PCIe reads and the CPU by timing)
  STRATA_PREFILL_CPU_SHARE=0   no timing-probed CPU share in the prompt read
  --lookup-max-t 0 --suffix-draft 0   no lookup windows: the draft policy (include/strata/spec/draft_policy.hpp) picks
                       between MTP and lookup windows by MEASURED round times, so with them on the window sizes vary run to run
  the CFG's --expert-cache (one slot count for both arms)

  python idcheck.py NAME --cfg runs/id/cfg-run.json --cand "STRATA_GR_UP_WIDE=1" [--ref "..."] [--aa] [--n 10] [--tokens 160]

An arm is ';'-separated key=value: exe=PATH replaces the CFG's engine, args=... appends engine arguments (space-separated),
any other key is an environment variable.  --aa scores the reference twice first (proves the setup is deterministic).
Writes runs/id/NAME/{set.json, ref.tsv, cand.tsv, result.json}.  Exit 0 identical, 1 different, 2 error.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
STRATA = Path(os.environ.get("STRATA_DIR") or LAB.parents[1])   # the Strata checkout; this lab sits in its sm86/lab
FC = STRATA / "tools" / "force_check.py"
PY = STRATA / ".venv" / "Scripts" / "python.exe"
PINS_ARGS = "--adapt-every 0 --pcie-frac {pcie} --lookup-max-t 0 --suffix-draft 0"
PINS_ENV = {"STRATA_PREFILL_CPU_SHARE": "0"}


def parse_arm(spec):
    exe, args, env = None, [], {}
    for part in [p for p in (spec or "").split(";") if p.strip()]:
        k, _, v = part.strip().partition("=")
        if k == "exe":
            exe = v
        elif k == "args":
            args += v.split()
        else:
            env[k] = v
    return exe, args, env


def subset(src, dst, n, tokens):
    st = json.load(open(src))
    items = st["items"]
    step = max(1, len(items) // n)
    pick = [dict(it, cont=it["cont"][:tokens]) for it in items[::step][:n]]
    json.dump({"config": st.get("config"), "env": st.get("env", []), "items": pick}, open(dst, "w"))
    return len(pick), sum(len(it["cont"]) for it in pick)


def score(cfg_path, spec, set_path, out, pcie):
    exe, args, env = parse_arm(spec)
    cfg = json.load(open(cfg_path, encoding="utf-8-sig"))
    if exe:
        cfg["exe"] = exe
    arm_cfg = out.with_suffix(".cfg.json")
    json.dump(cfg, open(arm_cfg, "w"), indent=1)
    cmd = [str(PY), str(FC), "score", str(arm_cfg), str(set_path), str(out), "--path", "decode",
           "--arg", PINS_ARGS.format(pcie=pcie) + (" " + " ".join(args) if args else "")]
    for k, v in {**PINS_ENV, **env}.items():
        cmd += ["--env", f"{k}={v}"]
    print("scoring", out.name, "|", spec or "(reference)", flush=True)
    r = subprocess.run(cmd, cwd=str(LAB), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-2000:], sep="\n")
        raise SystemExit(f"score failed for {out.name} (exit {r.returncode}); engine log: {out}.engine.log")
    return out


def decode_speed(tsv):
    """Forced-decode speed from the scoring engine's log: sum of generated tokens / sum of their ms (same text in every arm)."""
    import re
    tok = ms = 0
    for ln in open(str(tsv) + ".engine.log", encoding="utf-8", errors="replace"):
        m = re.search(r"(\d+) generated in (\d+) ms", ln)
        if m:
            tok, ms = tok + int(m.group(1)), ms + int(m.group(2))
    return round(1000.0 * tok / ms, 1) if ms else None


def compare(a, b):
    la, lb = open(a).read().splitlines(), open(b).read().splitlines()
    meta = json.load(open(str(a) + ".meta.json"))["items"]
    diff = [i for i in range(min(len(la), len(lb))) if la[i] != lb[i]]
    res = {"lines": [len(la), len(lb)], "differing_lines": len(diff) + abs(len(la) - len(lb)), "identical": not diff and len(la) == len(lb)}
    if diff:
        i = diff[0]
        item = next((m["id"] for m in meta if m["first_line"] <= i < m["end_line"]), "?")
        fa, fb = la[i].split("\t"), lb[i].split("\t")
        res["first_difference"] = {"line": i, "item": item, "ref": la[i][:160], "cand": lb[i][:160]}
        argmax_flips = sum(1 for j in diff if la[j].split("\t")[3] != lb[j].split("\t")[3])
        dl = [abs(float(la[j].split("\t")[2]) - float(lb[j].split("\t")[2])) for j in diff]
        res["argmax_flips"] = argmax_flips
        res["max_abs_logprob_diff"] = max(dl)
        res["first_item_with_difference"] = item
        del fa, fb
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--cfg", default=str(LAB / "runs" / "id" / "cfg-run.json"))
    ap.add_argument("--ref", default="")
    ap.add_argument("--cand", action="append", required=True, help="repeat for several candidates against one reference")
    ap.add_argument("--set", default=str(LAB / "runs" / "fc" / "set3A.json"))
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--tokens", type=int, default=160)
    ap.add_argument("--pcie", default="0.2")
    ap.add_argument("--aa", action="store_true")
    ap.add_argument("--reuse-ref", action="store_true", help="keep an existing ref.tsv from an earlier run of this NAME")
    a = ap.parse_args()
    d = LAB / "runs" / "id" / a.name
    d.mkdir(parents=True, exist_ok=True)
    sp = d / "set.json"
    n, toks = subset(a.set, sp, a.n, a.tokens)
    print(f"{n} items, {toks} forced tokens", flush=True)
    result = {"name": a.name, "cfg": a.cfg, "ref": a.ref, "items": n, "forced_tokens": toks, "pcie_frac": a.pcie, "cands": []}
    ref = d / "ref.tsv"
    if not (a.reuse_ref and ref.exists()):
        score(a.cfg, a.ref, sp, ref, a.pcie)
    if a.aa:
        ref2 = score(a.cfg, a.ref, sp, d / "ref2.tsv", a.pcie)
        result["aa"] = compare(ref, ref2)
        print("A/A:", json.dumps(result["aa"]), flush=True)
    rc = 0
    for i, spec in enumerate(a.cand):
        cand = score(a.cfg, spec, sp, d / f"cand{i}.tsv", a.pcie)
        r = compare(ref, cand)
        r["spec"] = spec
        r["decode_tps_ref"], r["decode_tps_cand"] = decode_speed(ref), decode_speed(cand)
        result["cands"].append(r)
        json.dump(result, open(d / "result.json", "w"), indent=1)
        print(("IDENTICAL  " if r["identical"] else "DIFFERENT  ") + spec + "  " +
              json.dumps({k: v for k, v in r.items() if k not in ("spec", "first_difference")}), flush=True)
        rc |= 0 if r["identical"] else 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
