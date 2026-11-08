"""Aggregate STRATA_DECODE_TIMING / STRATA_VERIFY_PROFILE lines of an engine log (window-weighted over all requests).

    python prof_parse.py <engine.log>
"""
import re
import sys
from collections import defaultdict

NUM = r"([0-9.]+)"
TIMING = re.compile(
    r"strata decode timing: (\d+) windows, avg T " + NUM + r", " + NUM + r" tokens/window, " + NUM + r" ms/window = "
    r"adapt wait " + NUM + r" \+ verify " + NUM + r" \(GPU-reach wait " + NUM + r" \+ per-layer host " + NUM +
    r" \[plan " + NUM + r" actq " + NUM + r" jobs " + NUM + r" CPU " + NUM + r"\] \+ stage " + NUM + r"\) \+ commit/emit " +
    NUM + r" \+ draft " + NUM + r" \+ adapt join " + NUM + r" \+ other " + NUM + r"; per layer-window: CPU experts " + NUM +
    r" \(" + NUM + r" entries\), VRAM hits " + NUM + r", PCIe " + NUM + r"; " + NUM + r" swaps/window")
FIELDS = ["T", "tok_per_win", "ms_per_win", "adapt_wait", "verify", "gpu_reach_wait", "per_layer_host", "plan", "actq",
          "jobs", "cpu", "stage", "commit_emit", "draft", "adapt_join", "other", "cpu_experts", "cpu_entries", "vram_hits",
          "pcie", "swaps"]


def main():
    text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
    tot_w, acc, n = 0, defaultdict(float), 0
    for m in TIMING.finditer(text):
        w = int(m.group(1))
        vals = [float(x) for x in m.groups()[1:]]
        for k, v in zip(FIELDS, vals):
            acc[k] += v * w
        tot_w += w
        n += 1
    if not tot_w:
        sys.exit("no 'strata decode timing' lines")
    avg = {k: acc[k] / tot_w for k in FIELDS}
    print(f"{n} requests, {tot_w} windows; window-weighted averages:")
    print(f"  window: T {avg['T']:.2f}, {avg['tok_per_win']:.2f} tokens/window, {avg['ms_per_win']:.2f} ms/window "
          f"-> {1000 * avg['tok_per_win'] / avg['ms_per_win']:.1f} tok/s")
    for k in ("adapt_wait", "verify", "gpu_reach_wait", "per_layer_host", "plan", "actq", "jobs", "cpu", "stage",
              "commit_emit", "draft", "adapt_join", "other"):
        ind = "    " if k in ("gpu_reach_wait", "per_layer_host", "stage") else "      " if k in ("plan", "actq", "jobs", "cpu") else "  "
        print(f"{ind}{k:16s} {avg[k]:7.2f} ms  ({100 * avg[k] / avg['ms_per_win']:5.1f}%)")
    print(f"  per layer-window: CPU experts {avg['cpu_experts']:.2f} ({avg['cpu_entries']:.2f} entries), VRAM hits "
          f"{avg['vram_hits']:.2f}, PCIe {avg['pcie']:.2f}; {avg['swaps']:.2f} swaps/window")
    stages = re.findall(r"strata decode GPU stages \(ms/window\):(.*)", text)
    if stages:
        agg, cnt = defaultdict(float), 0
        for s in stages:
            for name, v in re.findall(r"([A-Za-z][\w/+\-]*)\s+([0-9.]+)", s):
                agg[name] += float(v)
            cnt += 1
        print(f"  GPU stages (mean over {cnt} requests, ms/window): " +
              ", ".join(f"{k} {v / cnt:.2f}" for k, v in sorted(agg.items(), key=lambda kv: -kv[1])))
        print("  last GPU stage line:", stages[-1].strip()[:400])


if __name__ == "__main__":
    main()
