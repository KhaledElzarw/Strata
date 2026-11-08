"""Interleaved A/B of Strata engine settings on recorded real turns.

    python ab.py <experiment.json>

experiment.json:
  {"name": "drafter", "rounds": 3, "src": ["runs/requests/<tag>", ...], "limit": 40, "max_tokens": null,
   "seed": 1234, "temperature": null,
   "arms": [{"name": "mtp"}, {"name": "df2", "drafting": "dflash2", "set": {"--draft-conf": "0.5"}, "env": {...},
             "add": ["--adapt-async", "1"], "drop": ["--lookup-max-t"], "extra": {"strata_tune": {"pcie_frac": 0.35}}}]}

Each arm gets its own run config (the base config with its changes) and engine log. Arms alternate order every round
(A B / B A / A B ...). Each arm start: wait for /health loaded, one warm-up request, then the replay (replay.py's run),
then the server is stopped. Results: runs/replay/<name>-<arm>-r<k>.jsonl and runs/ab/<name>.json (per round stats, the
engine's cache slots and free VRAM, the GPU's peak temperature and power during the arm).
"""
import csv
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LAB = Path(__file__).parent
RUNS = LAB / "runs"
STRATA = Path(os.environ.get("STRATA_DIR") or LAB.parents[1])   # the Strata checkout; this lab sits in its sm86/lab
BASE_CFG = STRATA / "strata-iq3_xxs.json"
PY = STRATA / ".venv" / "Scripts" / "python.exe"
PORT = 19100
KILL = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*serve*server.py*' -or $_.Name -eq 'strata.exe' }"
        " | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")

sys.path.insert(0, str(LAB))
import replay  # noqa: E402


def stop_server():
    subprocess.run(["powershell", "-NoProfile", "-Command", KILL], capture_output=True)
    for _ in range(60):
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq strata.exe"], capture_output=True, text=True)
        if "strata.exe" not in r.stdout:
            return
        time.sleep(0.5)


def health():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=3) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return {}


def arm_config(exp: str, arm: dict, rnd: int) -> tuple[Path, Path]:
    cfg = json.load(open(BASE_CFG, encoding="utf-8"))
    args = list(cfg["args"])
    for flag in arm.get("drop", []):
        if flag in args:
            i = args.index(flag)
            nxt = args[i + 1] if i + 1 < len(args) else None
            del args[i:i + (2 if nxt is not None and not str(nxt).startswith("--") else 1)]
    for flag, val in arm.get("set", {}).items():
        if flag in args:
            args[args.index(flag) + 1] = str(val)
        else:
            args += [flag, str(val)]
    args += [str(x) for x in arm.get("add", [])]
    cfg["args"] = args
    if "exe" in arm:                # an engine build to test (e.g. C:/src/Strata/build-sm86/strata.exe)
        cfg["exe"] = arm["exe"]
    if "drafting" in arm:
        cfg["drafting"] = arm["drafting"]
    if "user_args" in arm:          # kept over the generated args at start, also by the drafter rules (e.g. --draft-conf / --spec for DFlash2)
        cfg["user_args"] = [str(x) for x in arm["user_args"]]
    logs = RUNS / "ab" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / f"{exp}-{arm['name']}-r{rnd}.engine.log"
    cfg["log"] = str(log)
    out = RUNS / "ab" / "configs" / f"{exp}-{arm['name']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(cfg, open(out, "w", encoding="utf-8"), indent=1)
    return out, log


def start_server(cfg_path: Path, env_extra: dict, console: Path, timeout=900):
    env = dict(os.environ, PYTHONUNBUFFERED="1", **{k: str(v) for k, v in env_extra.items()})
    p = subprocess.Popen([str(PY), str(STRATA / "serve" / "server.py"), "--engine", "strata", "--config", str(cfg_path),
                          "--port", str(PORT)], cwd=str(STRATA), env=env, stdout=open(console, "wb"),
                         stderr=subprocess.STDOUT)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if p.poll() is not None:
            raise SystemExit(f"server exited during start (see {console})")
        if health().get("loaded"):
            return p, round(time.time() - t0, 1)
        time.sleep(1)
    raise SystemExit("server never became ready")


def engine_facts(log: Path) -> dict:
    facts = {}
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return facts
    for line in text.splitlines():
        if "expert cache " in line and " slots, " in line and "GiB of VRAM" in line:
            facts["cache_slots"] = int(line.split("expert cache ")[1].split(" slots")[0])
        if "MiB of VRAM free with everything loaded" in line:
            facts["vram_free_mib"] = int(line.split("strata serve: ")[1].split(" MiB")[0])
        if "drafting:" in line or "DFlash2" in line and "[strata]" in line:
            facts.setdefault("drafting_lines", []).append(line.strip()[:160])
    return facts


def gpu_peak(t0: float, t1: float) -> dict:
    peak = {"temp_max": None, "power_max": None, "power_mean": None}
    try:
        rows = list(csv.reader(open(RUNS / "gpuwatch.csv", encoding="utf-8")))[1:]
    except OSError:
        return peak
    sel = []
    for r in rows:
        try:
            t = float(r[0])
            if t0 <= t <= t1:
                sel.append((float(r[2]), float(r[3])))
        except (ValueError, IndexError):
            continue
    if sel:
        peak = {"temp_max": max(s[0] for s in sel), "power_max": max(s[1] for s in sel),
                "power_mean": round(sum(s[1] for s in sel) / len(sel), 1)}
    return peak


METRIC_KEYS = ("expert_slots", "expert_cache_mib", "vram_free_mib", "spec", "mtp_max", "lookup", "pcie_frac", "spec_min_p",
               "pool_workers", "prefill_cap", "drafting", "drafting_note", "kv_resident")


def metrics() -> dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/metrics", timeout=5) as r:
            e = json.loads(r.read()).get("engine", {})
        return {f"m_{k}": e.get(k) for k in METRIC_KEYS}
    except Exception:  # noqa: BLE001
        return {}


def warmup():
    body = {"model": "x", "messages": [{"role": "user", "content": "Say hello in five words."}], "max_tokens": 32,
            "temperature": 0}
    try:
        replay.post(f"http://127.0.0.1:{PORT}/v1/chat/completions", body, 300)
    except Exception:  # noqa: BLE001
        pass


class Args:
    pass


def replay_arm(exp: dict, arm: dict, label: str) -> tuple[float, float]:
    rp = RUNS / "replay" / f"{label}.jsonl"
    if rp.exists():
        rp.unlink()
    t0 = time.time()
    for src in exp["src"]:
        a = Args()
        a.src, a.label, a.url = str(LAB / src), label, f"http://127.0.0.1:{PORT}"
        a.temperature, a.max_tokens, a.limit, a.repeat, a.timeout = (exp.get("temperature"), exp.get("max_tokens"),
                                                                     exp.get("limit"), 1, exp.get("timeout", 600))
        a.gap = exp.get("gap", 0)
        extra = dict(arm.get("extra", {}))
        if exp.get("seed"):
            extra["seed"] = exp["seed"]
        a.extra = json.dumps(extra) if extra else None
        replay.run(a)
    return t0, time.time()


def record(results, out, exp, rnd, arm, label, load_s, t0, t1, log, m):
    st = replay.stats(replay.load(label), 64)
    rec = {"round": rnd, "arm": arm["name"], "label": label, "load_s": load_s, "wall_s": round(t1 - t0, 1),
           **st, **engine_facts(log), **gpu_peak(t0, t1), **m, "m_vram_free_after": metrics().get("m_vram_free_mib")}
    results.append(rec)
    json.dump({"experiment": exp, "results": results}, open(out, "w", encoding="utf-8"), indent=1)
    print("AB", json.dumps({k: rec.get(k) for k in ("round", "arm", "median", "p10", "p90", "tok_weighted",
                                                    "accept", "timed", "m_expert_slots", "m_vram_free_mib",
                                                    "m_vram_free_after", "m_drafting", "temp_max", "power_max",
                                                    "errors", "load_s", "wall_s")}), flush=True)


def main():
    exp = json.load(open(sys.argv[1], encoding="utf-8"))
    name, arms, rounds = exp["name"], exp["arms"], exp.get("rounds", 3)
    results = []
    out = RUNS / "ab" / f"{name}.json"
    stop_server()
    if exp.get("same_server"):
        # arms differ only in per-request "extra" (strata_tune ...): one server start (exp["server"]: an arm's config
        # changes), the arms alternate A B / B A ... on it
        srv = dict(exp.get("server", {}), name="server")
        cfg, log = arm_config(name, srv, 0)
        p, load_s = start_server(cfg, srv.get("env", {}), log.with_suffix(".console.log"))
        warmup()
        m = metrics()
        for rnd in range(rounds):
            for arm in (arms if rnd % 2 == 0 else list(reversed(arms))):
                if (RUNS / "THERMAL_STOP").exists():
                    raise SystemExit("THERMAL_STOP present: aborting")
                label = f"{name}-{arm['name']}-r{rnd}"
                t0, t1 = replay_arm(exp, arm, label)
                record(results, out, exp, rnd, arm, label, load_s, t0, t1, log, m)
        stop_server()
        return summarize(out)
    for rnd in range(rounds):
        order = arms if rnd % 2 == 0 else list(reversed(arms))
        for arm in order:
            if (RUNS / "THERMAL_STOP").exists():
                raise SystemExit("THERMAL_STOP present: aborting")
            cfg, log = arm_config(name, arm, rnd)
            console = log.with_suffix(".console.log")
            try:
                p, load_s = start_server(cfg, arm.get("env", {}), console)
            except SystemExit as e:              # an arm that cannot start (e.g. a cache too big) is recorded, not fatal
                print("AB-FAIL", json.dumps({"round": rnd, "arm": arm["name"], "error": str(e)}), flush=True)
                results.append({"round": rnd, "arm": arm["name"], "label": None, "error": str(e), "median": None,
                                "tok_weighted": None})
                json.dump({"experiment": exp, "results": results}, open(out, "w", encoding="utf-8"), indent=1)
                stop_server()
                continue
            warmup()
            m = metrics()
            label = f"{name}-{arm['name']}-r{rnd}"
            t0, t1 = replay_arm(exp, arm, label)
            record(results, out, exp, rnd, arm, label, load_s, t0, t1, log, m)
            stop_server()
    summarize(out)


def paired(base_rows: list, rows: list) -> list:
    """Per-turn decode ratios (same request file, both timed with >= 64 tokens): candidate / base."""
    def tps(rs):
        return {r["file"]: r["timings"]["predicted_per_second"] for r in rs
                if r.get("timings") and (r["timings"].get("predicted_n") or 0) >= 64 and r["timings"].get("predicted_per_second")}
    b, c = tps(base_rows), tps(rows)
    return [c[k] / b[k] for k in sorted(b.keys() & c.keys())]


def paired_prefill(base_rows: list, rows: list) -> list:
    """Per-turn prompt-time ratios (same request file, both with new prompt tokens): candidate / base."""
    def pm(rs):
        return {r["file"]: r["timings"]["prompt_ms"] for r in rs
                if r.get("timings") and (r["timings"].get("prompt_n") or 0) > 0 and r["timings"].get("prompt_ms")}
    b, c = pm(base_rows), pm(rows)
    return [c[k] / b[k] for k in sorted(b.keys() & c.keys())]


def prefill_stats(rows: list) -> str:
    """Median prompt_ms over turns with new tokens, and prompt_ms = fixed + per-token fit over warm turns (cache_n > 0)."""
    t = [r["timings"] for r in rows if r.get("timings") and (r["timings"].get("prompt_n") or 0) > 0 and r["timings"].get("prompt_ms")]
    if not t:
        return "no prompt timings"
    ms = sorted(x["prompt_ms"] for x in t)
    w = [(x["prompt_n"], x["prompt_ms"]) for x in t if (x.get("cache_n") or 0) > 0]
    fit = ""
    if len(w) >= 5:
        mx, my = sum(a for a, _ in w) / len(w), sum(b for _, b in w) / len(w)
        sxx = sum((a - mx) ** 2 for a, _ in w)
        if sxx > 0:
            b1 = sum((a - mx) * (b - my) for a, b in w) / sxx
            fit = f", warm fit {my - b1 * mx:.0f} ms + {b1:.3f} ms/token (n={len(w)})"
    return f"median prompt {ms[len(ms) // 2]:.0f} ms (n={len(ms)}){fit}"


def ratio_ci(pr: list) -> str:
    import math
    import random
    logs = [math.log(x) for x in pr]
    boots = sorted(math.exp(sum(random.choice(logs) for _ in logs) / len(logs)) for _ in range(2000))
    return (f"{sorted(pr)[len(pr) // 2]:.3f}, geo-mean {math.exp(sum(logs) / len(logs)):.3f} "
            f"[95% {boots[50]:.3f}-{boots[1949]:.3f}]")


def summarize(path: Path):
    data = json.load(open(path, encoding="utf-8"))
    res = data["results"]
    arms = [a["name"] for a in data["experiment"]["arms"]]
    base = arms[0]
    print(f"== {data['experiment']['name']}: per-round median decode (tok/s), ratio vs {base}")
    by = {(r["round"], r["arm"]): r for r in res}
    rounds = sorted({r["round"] for r in res})
    for arm in arms:
        meds = [by[(k, arm)]["median"] for k in rounds if (k, arm) in by and by[(k, arm)]["median"]]
        ratios = [by[(k, arm)]["median"] / by[(k, base)]["median"] for k in rounds
                  if (k, arm) in by and (k, base) in by and by[(k, arm)]["median"] and by[(k, base)]["median"]]
        tw = [by[(k, arm)]["tok_weighted"] for k in rounds if (k, arm) in by and by[(k, arm)]["tok_weighted"]]
        pr = []
        for k in rounds:
            if (k, arm) in by and (k, base) in by and by[(k, arm)].get("label") and by[(k, base)].get("label"):
                pr += paired(replay.load(by[(k, base)]["label"]), replay.load(by[(k, arm)]["label"]))
        pm = None
        if pr:
            import math
            import random
            logs = [math.log(x) for x in pr]
            boots = sorted(math.exp(sum(random.choice(logs) for _ in logs) / len(logs)) for _ in range(2000))
            pm = (f"{sorted(pr)[len(pr) // 2]:.3f}, geo-mean {math.exp(sum(logs) / len(logs)):.3f} "
                  f"[95% {boots[50]:.3f}-{boots[1949]:.3f}]")
        rows_all, ppr = [], []
        for k in rounds:
            if (k, arm) in by and by[(k, arm)].get("label"):
                rows_all += replay.load(by[(k, arm)]["label"])
                if (k, base) in by and by[(k, base)].get("label") and arm != base:
                    ppr += paired_prefill(replay.load(by[(k, base)]["label"]), replay.load(by[(k, arm)]["label"]))
        pre = prefill_stats(rows_all) + (f"; paired prompt-time ratio {ratio_ci(ppr)} (n={len(ppr)})" if ppr else "")
        slots = [by[(k, arm)].get("m_expert_slots") for k in rounds if (k, arm) in by]
        acc = [by[(k, arm)].get("accept") for k in rounds if (k, arm) in by]
        print(f"  {arm:16s} medians {meds}  tok-weighted {tw}  ratio {[round(x, 3) for x in ratios]}  "
              f"paired-turn median ratio {pm} (n={len(pr)})  slots {slots}  accept {acc}")
        print(f"  {'':16s} prefill: {pre}")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--summary":
        summarize(Path(sys.argv[2]))
    else:
        main()
