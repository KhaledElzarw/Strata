"""Routing statistics from a STRATA_ROUTE_DUMP file: the CPU experts' bytes per layer, and how often a layer's CPU
experts repeat from earlier windows (issue #18: could the pool prefetch them while the GPU runs the dense chain?).

    python routestats.py <route dump> [--pack <checkout>/packs/iq3_xxs] [--json out.json]

The dump has one line per layer-window, "layer n_tok nd nmiss | e:rows:res ...": res 1 = resident in the GPU cache,
0 = a miss the CPU computes (unless the PCIe share takes it), 2 = tail-skipped. A window is a run of lines whose layer
index increases; the warm-up request's windows count like any other.
"""
import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

LAB = Path(__file__).resolve().parent
STRATA = Path(os.environ.get("STRATA_DIR") or LAB.parents[1])


def load_blobs(pack):
    """Per layer: (blob bytes, down bytes) from the pack's native_experts.txt."""
    rows = [l.split() for l in open(Path(pack) / "native_experts.txt", encoding="utf-8") if l.strip() and not l.startswith("#")]
    out = {}
    for r in rows:
        layer, gu, d, blob = int(r[0]), int(r[1]), int(r[2]), int(r[4])
        down = {20: 921_600, 42: 460_800}.get(d)   # IQ4_NL / Q2_0 down rows of 2560 x 640
        out[layer] = (blob, down if down is not None else 0, gu, d)
    return out


def windows(path):
    cur, last = {}, None
    for line in open(path, encoding="utf-8", errors="replace"):
        head, _, tail = line.partition("|")
        f = head.split()
        if len(f) < 4:
            continue
        layer = int(f[0])
        if last is not None and layer <= last and cur:
            yield cur
            cur = {}
        last = layer
        ents = []
        for tok in tail.split():
            e, rows, res = tok.split(":")
            ents.append((int(e), int(rows), int(res)))
        cur[layer] = (int(f[1]), ents)
    if cur:
        yield cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("--pack", default=str(STRATA / "packs" / "iq3_xxs"))
    ap.add_argument("--json")
    a = ap.parse_args()
    blobs = load_blobs(a.pack)
    W = list(windows(a.dump))
    K = (1, 2, 4, 8, 16)
    hist = defaultdict(list)          # layer -> list of miss sets, one per window
    st = defaultdict(float)
    per_layer_cpu = defaultdict(float)
    cover = {k: [0.0, 0.0, 0.0] for k in K}   # k -> [covered misses, covered bytes, predicted bytes]
    for w in W:
        for layer, (n_tok, ents) in w.items():
            miss = {e for e, _, res in ents if res == 0}
            st["layer_windows"] += 1
            st["routed"] += len(ents)
            st["miss"] += len(miss)
            st["skipped"] += sum(1 for _, _, res in ents if res == 2)
            st["miss_rows"] += sum(rows for _, rows, res in ents if res == 0)
            blob = blobs.get(layer, (0, 0, 0, 0))
            st["miss_bytes"] += blob[0] * len(miss)
            st["miss_down_bytes"] += blob[1] * len(miss)
            per_layer_cpu[layer] += len(miss)
            past = hist[layer]
            for k in K:
                pred = set().union(*past[-k:]) if past else set()
                hit = len(miss & pred)
                cover[k][0] += hit
                cover[k][1] += hit * blob[0]
                cover[k][2] += len(pred) * blob[0]
            past.append(miss)
    n = st["layer_windows"] or 1
    nw = len(W) or 1
    res = {
        "windows": len(W),
        "layer_windows": int(n),
        "cpu_experts_per_layer_window": st["miss"] / n,
        "cpu_rows_per_layer_window": st["miss_rows"] / n,
        "routed_per_layer_window": st["routed"] / n,
        "tail_skipped_per_layer_window": st["skipped"] / n,
        "cpu_mb_per_window": st["miss_bytes"] / nw / 1e6,
        "cpu_down_mb_per_window": st["miss_down_bytes"] / nw / 1e6,
        "repeat": {str(k): {"misses_covered": cover[k][0] / max(st["miss"], 1),
                             "bytes_covered": cover[k][1] / max(st["miss_bytes"], 1),
                             "predicted_mb_per_layer": cover[k][2] / n / 1e6} for k in K},
        "cpu_experts_by_layer": {str(l): per_layer_cpu[l] / nw for l in sorted(per_layer_cpu)},
    }
    print(f"{res['windows']} windows, {res['layer_windows']} layer-windows")
    print(f"per layer-window: {res['routed_per_layer_window']:.2f} routed, {res['cpu_experts_per_layer_window']:.2f} misses "
          f"({res['cpu_rows_per_layer_window']:.2f} token rows), {res['tail_skipped_per_layer_window']:.2f} tail-skipped "
          "(a miss runs on the CPU unless the PCIe share takes it)")
    print(f"miss bytes: {res['cpu_mb_per_window']:.1f} MB a window (down {res['cpu_down_mb_per_window']:.1f} MB)")
    print("a layer's misses that were misses at that layer in one of the last k windows:")
    for k in K:
        r = res["repeat"][str(k)]
        print(f"  k={k:2d}: {100 * r['misses_covered']:5.1f}% of misses, {100 * r['bytes_covered']:5.1f}% of bytes; "
              f"predicted set {r['predicted_mb_per_layer']:.1f} MB a layer")
    if a.json:
        json.dump(res, open(a.json, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
