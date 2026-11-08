"""Recompute every number the fork's README shows, from the raw files in runs/, and draw its charts.

    python readme_assets.py            (from sm86/lab; writes ../assets/results.json and ../assets/chart-*.svg)

Decode gains: per-turn decode ratios (candidate / base, the same recorded turn in the same round, both arms timed with
>= 64 tokens; ab.paired), pooled over the rounds of one A/B. Reported as the geometric mean of the ratios with a 95%
percentile bootstrap over turns (seeded, 4000 resamples) and the median ratio. Every A/B interleaves its arms
(A B / B A / A B) with a fresh engine per arm, on the 57 recorded agent turns of runs/replayset/hermes-v1.
The phase-1-vs-stock row is weaker evidence: the five phase-1 rounds and the two stock rounds ran on the same evening
(2026-11-07, after a reboot), one after the other, not interleaved; it pairs each turn's geometric mean over the rounds
of each arm.
Prefill: runs/cold/q3.jsonl (cold prompts, nothing reused). Window anatomy: STRATA_DECODE_TIMING lines of the prof8
timing arm (runs/ab/logs/prof8-q3tim-r*.engine.log), window-weighted.
Colors: the dataviz reference palette (light and dark steps), validated with its validate_palette.js.
"""
import json
import math
import random
import re
import statistics
import sys
from html import escape
from pathlib import Path

LAB = Path(__file__).resolve().parent
OUT = LAB.parent / "assets"
sys.path.insert(0, str(LAB))
import ab  # noqa: E402
import replay  # noqa: E402

SEED, BOOT = 20261108, 4000

STEPS = [  # (key, label, note, experiment, base arm, candidate arm, rounds)
    ("phase2", "Phase 2 switches", "HC down, PCIe copy, GEMV tables, expert layout",
     "ab3", "pre", "stack", 3),
    ("hc", "HC read kernels", "DOWN86 ring, up T-hybrid, computed xn", "hc86", "cur", "hc86", 3),
    ("q2", "Q2_0 expert down rows", "4 lanes a row, measured on the POOL_DAG arm", "dag1", "dag", "dagq2", 3),
    ("tier5", "Tier 5", "doorbell, fused hits, CPU-free tokens, DOWN87",
     "tier5", "q2", "q3", 3),
]
NOT_ADOPTED = [("res", "Resident HC read (STRATA_GR_RES)", "res", "q3", "q3res", 3),
               ("dag", "CPU pool as one batch per layer (STRATA_POOL_DAG)", "dag1", "hc86", "dag", 3)]
EXTRA = [("q2_over_base", "Q2_0 down rows over the plain base (no POOL_DAG)", "dag1", "hc86", "dagq2", 3)]
Q3_LABELS = [f"tier5-q3-r{k}" for k in range(3)] + [f"res-q3-r{k}" for k in range(3)]
RE_HIT = re.compile(r"decode expert cache hit rate: [\d.]+% \((\d+) hits / (\d+) lookups\)")


def prompt_time_ratio(exp, base, cand, rounds):
    ratios = []
    for k in range(rounds):
        ratios += ab.paired_prefill(replay.load(f"{exp}-{base}-r{k}"), replay.load(f"{exp}-{cand}-r{k}"))
    return paired_stats(ratios)


def warm_prompt():
    """Median prompt time of the q3 turns that read new tokens, and prompt_ms = fixed + per-token over warm turns."""
    t = [r["timings"] for lab in Q3_LABELS for r in replay.load(lab)
         if r.get("timings") and (r["timings"].get("prompt_n") or 0) > 0 and r["timings"].get("prompt_ms")]
    w = [(x["prompt_n"], x["prompt_ms"]) for x in t if (x.get("cache_n") or 0) > 0]
    mx, my = sum(a for a, _ in w) / len(w), sum(b for _, b in w) / len(w)
    b1 = sum((a - mx) * (b - my) for a, b in w) / sum((a - mx) ** 2 for a, _ in w)
    return {"turns": len(t), "median_prompt_ms": statistics.median(x["prompt_ms"] for x in t),
            "warm_turns": len(w), "fixed_ms": my - b1 * mx, "ms_per_new_token": b1}


def hit_rate():
    hits = lookups = 0
    for log in sorted((LAB / "runs" / "ab" / "logs").glob("res-q3-r*.engine.log")):
        for m in RE_HIT.finditer(log.read_text(encoding="utf-8", errors="replace")):
            hits += int(m.group(1)); lookups += int(m.group(2))
    return {"hits": hits, "lookups": lookups, "rate": hits / lookups if lookups else None}


def boot_ci(ratios):
    rng = random.Random(SEED)
    logs = [math.log(x) for x in ratios]
    means = sorted(sum(rng.choice(logs) for _ in logs) / len(logs) for _ in range(BOOT))
    return math.exp(means[int(0.025 * BOOT)]), math.exp(means[int(0.975 * BOOT) - 1])


def paired_stats(ratios):
    lo, hi = boot_ci(ratios)
    return {"n": len(ratios), "geo_mean": math.exp(sum(map(math.log, ratios)) / len(ratios)),
            "ci95": [lo, hi], "median": statistics.median(ratios)}


def round_medians(exp, arm, rounds):
    out = []
    for k in range(rounds):
        rows = replay.load(f"{exp}-{arm}-r{k}")
        tps = [r["timings"]["predicted_per_second"] for r in rows
               if r.get("timings") and (r["timings"].get("predicted_n") or 0) >= 64]
        out.append(round(statistics.median(tps), 1))
    return out


def ab_step(exp, base, cand, rounds):
    ratios = []
    for k in range(rounds):
        ratios += ab.paired(replay.load(f"{exp}-{base}-r{k}"), replay.load(f"{exp}-{cand}-r{k}"))
    s = paired_stats(ratios)
    s.update(base_round_medians=round_medians(exp, base, rounds), cand_round_medians=round_medians(exp, cand, rounds))
    return s


def phase1_vs_stock():
    def per_turn(labels):
        acc = {}
        for lab in labels:
            for r in replay.load(lab):
                t = r.get("timings") or {}
                if (t.get("predicted_n") or 0) >= 64 and t.get("predicted_per_second"):
                    acc.setdefault(r["file"], []).append(t["predicted_per_second"])
        return {k: math.exp(sum(map(math.log, v)) / len(v)) for k, v in acc.items()}
    p1 = ["e5b-c65-r0", "e5b-c65-r1", "e5b-c65-r2", "e7-c65-r0", "e7-c65-r1"]
    st = ["e8-stock-r0", "e8-stock-r1"]
    a, b = per_turn(st), per_turn(p1)
    s = paired_stats([b[k] / a[k] for k in sorted(a.keys() & b.keys())])
    s.update(base_round_medians=round_medians("e8", "stock", 2),
             cand_round_medians=round_medians("e5b", "c65", 3) + round_medians("e7", "c65", 2))
    return s


RE_WIN = re.compile(r"strata decode timing: (\d+) windows, avg T ([\d.]+), ([\d.]+) tokens/window, ([\d.]+) ms/window = "
                    r"adapt wait ([\d.]+) \+ verify ([\d.]+) \(GPU-reach wait ([\d.]+) \+ per-layer host ([\d.]+) "
                    r"\[plan ([\d.]+) actq ([\d.]+) jobs ([\d.]+) CPU ([\d.]+)\] \+ stage ([\d.]+)\) \+ commit/emit ([\d.]+) "
                    r"\+ draft ([\d.]+) \+ adapt join ([\d.]+) \+ other ([\d.]+)")


def window_anatomy():
    keys = ["T", "tokens", "ms", "adapt_wait", "verify", "gpu_wait", "host", "plan", "actq", "jobs", "cpu", "stage",
            "commit", "draft", "adapt_join", "other"]
    tot, n = dict.fromkeys(keys, 0.0), 0
    for log in sorted((LAB / "runs" / "ab" / "logs").glob("prof8-q3tim-r*.engine.log")):
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            m = RE_WIN.search(line)
            if m:
                w = int(m.group(1)); n += w
                for k, v in zip(keys, m.groups()[1:]):
                    tot[k] += w * float(v)
    a = {k: v / n for k, v in tot.items()}
    parts = [("Waiting for the GPU (dense chain)", a["gpu_wait"]), ("CPU expert step", a["cpu"]), ("Drafting (DFlash2)", a["draft"]),
             ("Other verify work", a["verify"] - a["gpu_wait"] - a["host"]),
             ("Other host work", a["plan"] + a["actq"] + a["jobs"] + a["stage"] + a["adapt_wait"] + a["commit"]
              + a["adapt_join"] + a["other"])]
    return {"windows": n, "avg_T": a["T"], "tokens_per_window": a["tokens"], "ms_per_window": a["ms"],
            "tok_s_in_windows": 1000 * a["tokens"] / a["ms"], "parts_ms": parts}


def prefill():
    rows = [json.loads(x) for x in (LAB / "runs" / "cold" / "q3.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    out = []
    for size in sorted({r["size"] for r in rows}):
        v = [r["prompt_tps"] for r in rows if r["size"] == size]
        s = [r["prompt_ms"] / 1000 for r in rows if r["size"] == size]
        out.append({"size": size, "tok_s": v, "median": statistics.median(v), "seconds": s})
    return out


# ---------------------------------------------------------------- charts
THEMES = {
    "light": dict(surface="#fcfcfb", ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9", axis="#c3c2b7",
                  ring="rgba(11,11,11,0.10)", s1="#2a78d6", cats=["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"],
                  on=["#ffffff", "#ffffff", "#ffffff", "#0b0b0b", "#ffffff"]),
    "dark": dict(surface="#1a1a19", ink="#f0efec", ink2="#c3c2b7", muted="#898781", grid="#2c2c2a", axis="#383835",
                 ring="rgba(255,255,255,0.10)", s1="#3987e5", cats=["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"],
                 on=["#ffffff", "#ffffff", "#ffffff", "#ffffff", "#ffffff"]),
}
FONT = "system-ui, -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


def svg(w, h, t, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="{escape(title)}" font-family="{FONT}">\n<title>{escape(title)}</title>\n'
            f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="12" fill="{t["surface"]}" stroke="{t["ring"]}"/>\n'
            + body + "\n</svg>\n")


def bar_path(x0, y, x1, h, r=4):
    """A horizontal bar square at the baseline x0 and rounded (r) at its data end x1."""
    if x1 - x0 < r:
        r = max(0.0, x1 - x0)
    return (f"M{x0:.1f},{y:.1f} H{x1 - r:.1f} Q{x1:.1f},{y:.1f} {x1:.1f},{y + r:.1f} V{y + h - r:.1f} "
            f"Q{x1:.1f},{y + h:.1f} {x1 - r:.1f},{y + h:.1f} H{x0:.1f} Z")


def col_path(x, y0, y1, w, r=4):
    """A vertical column square at the baseline y0 and rounded at its top y1."""
    return (f"M{x:.1f},{y0:.1f} V{y1 + r:.1f} Q{x:.1f},{y1:.1f} {x + r:.1f},{y1:.1f} H{x + w - r:.1f} "
            f"Q{x + w:.1f},{y1:.1f} {x + w:.1f},{y1 + r:.1f} V{y0:.1f} Z")


def pct(x):
    return f"{(x - 1) * 100:+.1f}%"


def chart_gains(rows, t):
    W, left, right, top, rowh = 860, 300, 150, 64, 58
    H = top + rowh * len(rows) + 70
    xmax = 10.0
    sx = lambda p: left + (W - left - right) * p / xmax  # noqa: E731
    b = [f'<text x="24" y="34" font-size="15" font-weight="600" fill="{t["ink"]}">Decode gain of each adopted step</text>',
         f'<text x="24" y="52" font-size="12" fill="{t["ink2"]}">Paired A/B on 57 recorded agent turns: geometric mean of '
         f'per-turn ratios, 95% bootstrap CI</text>']
    for p in range(0, 11, 2):
        x = sx(p)
        b.append(f'<line x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" y2="{top + rowh * len(rows)}" stroke="{t["grid"]}" stroke-width="1"/>')
        b.append(f'<text x="{x:.1f}" y="{top + rowh * len(rows) + 18}" font-size="11" text-anchor="middle" '
                 f'fill="{t["muted"]}" style="font-variant-numeric: tabular-nums">{p}%</text>')
    b.append(f'<line x1="{sx(0):.1f}" y1="{top - 6}" x2="{sx(0):.1f}" y2="{top + rowh * len(rows)}" stroke="{t["axis"]}" stroke-width="1"/>')
    for i, r in enumerate(rows):
        y = top + i * rowh + 10
        g, (lo, hi) = (r["geo_mean"] - 1) * 100, [(v - 1) * 100 for v in r["ci95"]]
        color = t["muted"] if r.get("weak") else t["s1"]
        b.append(f'<text x="24" y="{y + 9}" font-size="13" font-weight="600" fill="{t["ink"]}">{escape(r["label"])}</text>')
        b.append(f'<text x="24" y="{y + 26}" font-size="11" fill="{t["muted"]}">{escape(r["sub"])}</text>')
        b.append(f'<path d="{bar_path(sx(0), y, sx(g), 20)}" fill="{color}"><title>{escape(r["label"])}: '
                 f'{g:+.1f}% (95% CI {lo:+.1f} to {hi:+.1f}%, n={r["n"]} turn pairs)</title></path>')
        yc = y + 10
        b.append(f'<line x1="{sx(max(lo, -0.4)):.1f}" y1="{yc}" x2="{sx(hi):.1f}" y2="{yc}" stroke="{t["ink2"]}" stroke-width="1.5"/>')
        for e in (max(lo, -0.4), hi):
            b.append(f'<line x1="{sx(e):.1f}" y1="{yc - 6}" x2="{sx(e):.1f}" y2="{yc + 6}" stroke="{t["ink2"]}" stroke-width="1.5"/>')
        b.append(f'<text x="{sx(max(hi, g)) + 10:.1f}" y="{yc + 4}" font-size="13" font-weight="600" fill="{t["ink"]}" '
                 f'style="font-variant-numeric: tabular-nums">{g:+.1f}%<tspan font-weight="400" fill="{t["ink2"]}" '
                 f'font-size="11"> ({lo:+.1f} to {hi:+.1f})</tspan></text>')
    b.append(f'<text x="24" y="{H - 18}" font-size="11" fill="{t["muted"]}">Gray row: same evening, rounds run one after '
             f'the other (not interleaved). Blue rows: interleaved arms, fresh engine per arm.</text>')
    return svg(W, H, t, "\n".join(b), "Decode gain of each adopted step")


def chart_prefill(pf, t):
    W, H, left, top, bottom = 860, 330, 70, 70, 60
    ymax = 3500
    plot_h = H - top - bottom
    sy = lambda v: top + plot_h * (1 - v / ymax)  # noqa: E731
    b = [f'<text x="24" y="34" font-size="15" font-weight="600" fill="{t["ink"]}">Cold prompt throughput</text>',
         f'<text x="24" y="52" font-size="12" fill="{t["ink2"]}">Prompt tokens per second, nothing reused; bar = median '
         f'of {len(pf[0]["tok_s"])} runs, whisker = range, seconds below</text>']
    for v in range(0, ymax + 1, 500):
        y = sy(v)
        b.append(f'<line x1="{left}" y1="{y:.1f}" x2="{W - 24}" y2="{y:.1f}" stroke="{t["axis"] if v == 0 else t["grid"]}" stroke-width="1"/>')
        b.append(f'<text x="{left - 10}" y="{y + 4:.1f}" font-size="11" text-anchor="end" fill="{t["muted"]}" '
                 f'style="font-variant-numeric: tabular-nums">{v:,}</text>')
    band = (W - 24 - left) / len(pf)
    for i, p in enumerate(pf):
        cx = left + band * (i + 0.5)
        y1 = sy(p["median"])
        b.append(f'<path d="{col_path(cx - 12, sy(0), y1, 24)}" fill="{t["s1"]}"><title>{p["size"] // 1024}K tokens: '
                 f'median {p["median"]:,.0f} tok/s (runs: {", ".join(f"{v:,.0f}" for v in p["tok_s"])})</title></path>')
        lo, hi = min(p["tok_s"]), max(p["tok_s"])
        b.append(f'<line x1="{cx:.1f}" y1="{sy(lo):.1f}" x2="{cx:.1f}" y2="{sy(hi):.1f}" stroke="{t["ink2"]}" stroke-width="1.5"/>')
        for v in (lo, hi):
            b.append(f'<line x1="{cx - 6:.1f}" y1="{sy(v):.1f}" x2="{cx + 6:.1f}" y2="{sy(v):.1f}" stroke="{t["ink2"]}" stroke-width="1.5"/>')
        b.append(f'<text x="{cx + 18:.1f}" y="{y1 + 4:.1f}" font-size="13" font-weight="600" fill="{t["ink"]}">'
                 f'{p["median"]:,.0f}</text>')
        b.append(f'<text x="{cx:.1f}" y="{H - bottom + 20}" font-size="12" text-anchor="middle" fill="{t["ink2"]}">'
                 f'{p["size"] // 1024}K tokens</text>')
        b.append(f'<text x="{cx:.1f}" y="{H - bottom + 36}" font-size="11" text-anchor="middle" fill="{t["muted"]}">'
                 f'{statistics.median(p["seconds"]):.1f} s</text>')
    return svg(W, H, t, "\n".join(b), "Cold prompt throughput by prompt length")


def chart_window(wa, t):
    W, H, x0, y0, bh = 860, 210, 24, 92, 28
    total = sum(v for _, v in wa["parts_ms"])
    width = W - 2 * x0
    b = [f'<text x="24" y="34" font-size="15" font-weight="600" fill="{t["ink"]}">Where one decode window goes: '
         f'{wa["ms_per_window"]:.1f} ms for {wa["tokens_per_window"]:.2f} kept tokens</text>',
         f'<text x="24" y="52" font-size="12" fill="{t["ink2"]}">Engine timing over {wa["windows"]:,} windows of real '
         f'turns, as the host sees it ({wa["tok_s_in_windows"]:.0f} tok/s inside the windows)</text>']
    x = x0
    for i, (name, v) in enumerate(wa["parts_ms"]):
        w = width * v / total
        gap = 2 if i < len(wa["parts_ms"]) - 1 else 0
        b.append(f'<rect x="{x:.1f}" y="{y0}" width="{max(w - gap, 0.5):.1f}" height="{bh}" rx="4" fill="{t["cats"][i]}">'
                 f'<title>{escape(name)}: {v:.2f} ms ({100 * v / total:.0f}%)</title></rect>')
        label = f"{v:.1f} ms"
        if w - gap > 7.2 * len(label) + 16:
            b.append(f'<text x="{x + 8:.1f}" y="{y0 + 19}" font-size="12" font-weight="600" fill="{t["on"][i]}">{label}</text>')
        x += w
    lx, ly = x0, y0 + bh + 34
    for i, (name, v) in enumerate(wa["parts_ms"]):
        item = f"{name}"
        b.append(f'<rect x="{lx}" y="{ly - 10}" width="10" height="10" rx="2" fill="{t["cats"][i]}"/>')
        b.append(f'<text x="{lx + 16}" y="{ly}" font-size="12" fill="{t["ink2"]}">{escape(item)}</text>')
        lx += 16 + 7.0 * len(item) + 26
        if lx > W - 200:
            lx, ly = x0, ly + 22
    return svg(W, H, t, "\n".join(b), "Where one decode window goes")


def main():
    steps = []
    p1 = phase1_vs_stock()
    p1.update(key="phase1", label="Phase 1 config vs stock", sub="DFlash2 pack, explicit expert cache", weak=True)
    steps.append(p1)
    for key, label, note, exp, base, cand, rounds in STEPS:
        s = ab_step(exp, base, cand, rounds)
        s.update(key=key, label=label, sub=note)
        steps.append(s)
    others = []
    for key, label, exp, base, cand, rounds in NOT_ADOPTED:
        s = ab_step(exp, base, cand, rounds)
        s.update(key=key, label=label)
        others.append(s)
    for key, label, exp, base, cand, rounds in EXTRA:
        s = ab_step(exp, base, cand, rounds)
        s.update(key=key, label=label)
        others.append(s)
    compounded = math.prod(s["geo_mean"] for s in steps[1:])
    res = {"steps": steps, "not_adopted": others, "compounded_over_phase1": compounded,
           "compounded_over_stock": compounded * steps[0]["geo_mean"],
           "q3_round_medians": round_medians("tier5", "q3", 3) + round_medians("res", "q3", 3),
           "prefill": prefill(), "window": window_anatomy(),
           "phase2_prompt_time_ratio": prompt_time_ratio("ab3", "pre", "stack", 3),
           "q3_warm_prompt": warm_prompt(), "q3_decode_hit_rate": hit_rate()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    for mode, t in THEMES.items():
        (OUT / f"chart-gains-{mode}.svg").write_text(chart_gains(steps, t), encoding="utf-8")
        (OUT / f"chart-prefill-{mode}.svg").write_text(chart_prefill(res["prefill"], t), encoding="utf-8")
        (OUT / f"chart-window-{mode}.svg").write_text(chart_window(res["window"], t), encoding="utf-8")
    for s in steps + others:
        print(f"{s['label']:52s} n={s['n']:3d} geo {pct(s['geo_mean'])} [{pct(s['ci95'][0])}, {pct(s['ci95'][1])}] "
              f"median {pct(s['median'])}  base {s['base_round_medians']} cand {s['cand_round_medians']}")
    print(f"compounded over phase 1 {pct(compounded)}, over stock {pct(res['compounded_over_stock'])}")
    print("q3 round medians", res["q3_round_medians"])
    for p in res["prefill"]:
        print(f"prefill {p['size']:6d}: median {p['median']:,.0f} tok/s, runs {[round(v) for v in p['tok_s']]}")
    pt = res["phase2_prompt_time_ratio"]
    print(f"phase-2 prompt time {pct(pt['geo_mean'])} [{pct(pt['ci95'][0])}, {pct(pt['ci95'][1])}] n={pt['n']}")
    print("q3 warm prompt", {k: round(v, 3) for k, v in res["q3_warm_prompt"].items()}, "| hit rate", res["q3_decode_hit_rate"])
    w = res["window"]
    print(f"window: {w['windows']} windows, T {w['avg_T']:.2f}, {w['tokens_per_window']:.2f} tok/win, {w['ms_per_window']:.2f} ms",
          [(n, round(v, 2)) for n, v in w["parts_ms"]])


if __name__ == "__main__":
    main()
