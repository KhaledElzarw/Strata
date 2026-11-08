"""GPU busy time, idle gaps and the top kernels in the DECODE parts of an nsys cuda_gpu_trace CSV (nsyscap.py writes it).

    python nsysan.py runs/nsys/NAME_cuda_gpu_trace.csv [--top 40] [--all]

Decode parts = the stretches of at least 100 ms with no prompt-path op (MMQ, cuBLAS / CUTLASS GEMMs, strata::prefill::,
prompt attention, HtoD memcpys of the prompt path's expert streaming); --all takes the whole trace.  Busy = the union of
kernel and memcpy intervals over all streams; a gap is time with nothing running on the GPU.  Per kernel (template and
parameter lists folded): count, total ms, mean us, share of busy time, and per decode window when the windows can be
counted (gr_down82 / gr_down86 / staged down launches / 97 HC reads a window).
"""
import argparse
import csv
import re
from collections import defaultdict

PREFILL = re.compile(r"mul_mat_q|cutlass|prefill::|prompt_attn|s16816gemm|quantize_mmq")


def fold(name):
    s = name.replace("(anonymous namespace)", "anon")
    while re.search(r"<[^<>]*>", s):
        s = re.sub(r"<[^<>]*>", "", s)
    s = s.split("(")[0]
    s = s.replace("void ", "").replace("strata::kernels::", "").replace("anon::", "")
    return s.strip()[:80]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args()
    rows = []
    with open(a.csv, encoding="utf-8", errors="replace") as f:
        r = csv.DictReader(f)
        ks = next(c for c in r.fieldnames if c.startswith("Start"))
        kd = next(c for c in r.fieldnames if c.startswith("Duration"))
        for x in r:
            try:
                rows.append((int(x[ks]), int(x[kd]), x.get("Name", "?")))
            except (ValueError, KeyError):
                continue
    rows.sort()
    if not a.all:   # decode stretches: >= 100 ms between prompt-path ops
        pf = [s for s, d, n in rows if PREFILL.search(n)]
        bounds, prev = [], rows[0][0]
        for s in pf + [rows[-1][0] + 1]:
            if s - prev >= 100_000_000:
                bounds.append((prev, s))
            prev = max(prev, s)
        keep = []
        j = 0
        for s, d, n in rows:
            while j < len(bounds) and s >= bounds[j][1]:
                j += 1
            if j < len(bounds) and bounds[j][0] < s and not PREFILL.search(n) and "memcpy Host-to-Device" not in n:
                keep.append((s, d, n, j))
        print(f"decode stretches: {len(bounds)}, " + ", ".join(f"{(b - a2) / 1e6:.0f} ms" for a2, b in bounds))
    else:
        keep = [(s, d, n, 0) for s, d, n in rows]
    span = busy = 0
    gaps = []
    by_seg = defaultdict(list)
    for x in keep:
        by_seg[x[3]].append(x)
    for seg in by_seg.values():
        span += seg[-1][0] + seg[-1][1] - seg[0][0]
        cs, ce = seg[0][0], seg[0][0] + seg[0][1]
        for s, d, _, _ in seg[1:]:
            if s > ce:
                busy += ce - cs
                gaps.append(s - ce)
                cs, ce = s, s + d
            else:
                ce = max(ce, s + d)
        busy += ce - cs
    tot = defaultdict(lambda: [0, 0])
    for s, d, n, _ in keep:
        g = tot[fold(n)]
        g[0] += 1
        g[1] += d
    hc = sum(c for n, (c, d) in tot.items() if "gr_down82" in n or "gr_down86" in n or "gr_down_staged" in n)
    win = hc / 97 if hc else 0
    print(f"{len(keep)} GPU ops over {span / 1e6:.1f} ms; busy {busy / 1e6:.1f} ms ({100 * busy / max(1, span):.1f}%), "
          f"idle {(span - busy) / 1e6:.1f} ms in {len(gaps)} gaps" + (f"; ~{win:.0f} windows, {span / 1e6 / win:.2f} ms/window, "
                                                                     f"{len(keep) / win:.0f} ops/window" if win else ""))
    gs = sorted(gaps)
    if gs:
        q = lambda p: gs[min(len(gs) - 1, int(p * len(gs)))] / 1e3
        bins = [(0, 2_000), (2_000, 10_000), (10_000, 50_000), (50_000, 200_000), (200_000, 10**15)]
        parts = [f"{lo / 1e3:.0f}-{hi / 1e3:.0f}us {sum(g for g in gs if lo <= g < hi) / 1e6:.1f} ms" for lo, hi in bins]
        print(f"gaps us: p50 {q(0.5):.2f} p90 {q(0.9):.2f} p99 {q(0.99):.1f}; idle by gap size: " + ", ".join(parts))
    print(f"{'kernel':80s} {'count':>8s} {'ms':>8s} {'us/op':>7s} {'%busy':>6s}" + (f" {'ms/win':>7s}" if win else ""))
    for n, (c, d) in sorted(tot.items(), key=lambda x: -x[1][1])[:a.top]:
        print(f"{n:80s} {c:8d} {d / 1e6:8.1f} {d / c / 1e3:7.1f} {100 * d / max(1, busy):6.1f}" + (f" {d / 1e6 / win:7.3f}" if win else ""))


if __name__ == "__main__":
    main()
