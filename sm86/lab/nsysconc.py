"""Per-stream activity and cross-stream overlap in the DECODE parts of an nsys sqlite export.

    python nsysconc.py runs/nsys/NAME.sqlite [--top 6] [--main STREAM]

(`nsys export --type sqlite -o NAME.sqlite NAME.nsys-rep`.)  Decode parts as in nsysan.py (stretches of >= 100 ms with
no prompt-path op).  Per stream: kernel count, busy ms (union of its kernels and memcpys), the spin share
(wait_flag_ge* kernels: the GPU waiting for a host or cross-stream flag) and its top kernels.  The main stream is the
one with the most HC-read kernels (or --main).  For every other stream: how much of its busy time falls while the main
stream runs real work (contention), while the main stream spins, and while the main stream has nothing running.
Per window = / (HC-read kernels on the main stream / 97).
"""
import argparse
import bisect
import re
import sqlite3
from collections import defaultdict

PREFILL = re.compile(r"mul_mat_q|cutlass|prefill::|prompt_attn|s16816gemm|quantize_mmq")
HC = re.compile(r"gr_down8[0-9]_kernel|gr_down_staged|gr_res_kernel")
SPIN = re.compile(r"wait_flag_ge")


def fold(name):
    s = name.replace("(anonymous namespace)", "anon")
    while re.search(r"<[^<>]*>", s):
        s = re.sub(r"<[^<>]*>", "", s)
    s = s.split("(")[0].replace("void ", "").replace("strata::kernels::", "").replace("anon::", "")
    return s.strip()[:60]


def union(iv):
    """Sorted, merged intervals."""
    out = []
    for s, e in sorted(iv):
        if out and s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1][1] = e
        else:
            out.append([s, e])
    return out


def total(iv):
    return sum(e - s for s, e in iv)


def inter(a, b):
    """Total length of the intersection of two merged interval lists."""
    i = j = t = 0
    while i < len(a) and j < len(b):
        s, e = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if s < e:
            t += e - s
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--main", type=int)
    ap.add_argument("--streams", type=int, default=12, help="streams listed (by busy time)")
    a = ap.parse_args()
    db = sqlite3.connect(a.db)
    names = dict(db.execute("SELECT id, value FROM StringIds"))
    ops = [(s, e, st, names.get(n, "?")) for s, e, st, n in
           db.execute("SELECT start, end, streamId, demangledName FROM CUPTI_ACTIVITY_KIND_KERNEL")]
    for s, e, st, k in db.execute("SELECT start, end, streamId, copyKind FROM CUPTI_ACTIVITY_KIND_MEMCPY"):
        ops.append((s, e, st, f"memcpy kind {k}"))
    ops.sort()
    pf = [s for s, e, st, n in ops if PREFILL.search(n)]
    bounds, prev = [], ops[0][0]
    for s in pf + [ops[-1][0] + 1]:
        if s - prev >= 100_000_000:
            bounds.append((prev, s))
        prev = max(prev, s)
    keep, j = [], 0
    for x in ops:
        while j < len(bounds) and x[0] >= bounds[j][1]:
            j += 1
        if j < len(bounds) and bounds[j][0] < x[0] and not PREFILL.search(x[3]) and x[3] != "memcpy kind 1":   # 1 = HtoD
            keep.append(x)
    span = sum(b - a2 for a2, b in bounds)
    print(f"decode stretches: {len(bounds)}, {span / 1e6:.0f} ms; {len(keep)} GPU ops")
    by = defaultdict(list)
    for x in keep:
        by[x[2]].append(x)
    hc = {st: sum(1 for x in v if HC.search(x[3])) for st, v in by.items()}
    main_st = a.main if a.main is not None else max(hc, key=hc.get)
    win = hc[main_st] / 97 if hc[main_st] else 0
    print(f"main stream {main_st}: {hc[main_st]} HC reads, ~{win:.0f} windows, {span / 1e6 / max(win, 1):.2f} ms/window")
    pw = (lambda ns: ns / 1e6 / win) if win else (lambda ns: ns / 1e6)
    unit = "ms/win" if win else "ms"
    m_all = union([(s, e) for s, e, st, n in by[main_st]])
    m_spin = union([(s, e) for s, e, st, n in by[main_st] if SPIN.search(n)])
    m_work = union([(s, e) for s, e, st, n in by[main_st] if not SPIN.search(n)])
    all_busy = union([(s, e) for s, e, st, n in keep])
    real_busy = union([(s, e) for s, e, st, n in keep if not SPIN.search(n)])
    print(f"GPU: any op {pw(total(all_busy)):.2f} {unit}, real work (no spin) {pw(total(real_busy)):.2f}, "
          f"nothing {pw(span - total(all_busy)):.2f}")
    print(f"main: work {pw(total(m_work)):.2f} {unit}, spin {pw(total(m_spin)):.2f}, "
          f"idle {pw(span - total(m_all)):.2f}")
    order = sorted(by, key=lambda st: -sum(e - s for s, e, _, _ in by[st]))
    rest = order[a.streams:]
    if rest:
        print(f"({len(rest)} more streams, {pw(sum(e - s for st in rest for s, e, _, _ in by[st])):.2f} {unit} of ops, not listed)")
    for st in order[:a.streams]:
        v = by[st]
        iv = union([(s, e) for s, e, _, _ in v])
        spin = union([(s, e) for s, e, _, n in v if SPIN.search(n)])
        work = union([(s, e) for s, e, _, n in v if not SPIN.search(n)])
        k = defaultdict(lambda: [0, 0])
        for s, e, _, n in v:
            g = k[fold(n)]
            g[0] += 1
            g[1] += e - s
        top = ", ".join(f"{n} {pw(d):.2f}" for n, (c, d) in sorted(k.items(), key=lambda x: -x[1][1])[:a.top])
        line = (f"stream {st}{' (main)' if st == main_st else ''}: {len(v)} ops, busy {pw(total(iv)):.2f} {unit} "
                f"(work {pw(total(work)):.2f}, spin {pw(total(spin)):.2f})")
        if st != main_st:
            w_mw = inter(work, m_work)
            w_ms = inter(work, m_spin)
            line += (f"; its work while main works {pw(w_mw):.2f}, while main spins {pw(w_ms):.2f}, "
                     f"while main idle {pw(total(work) - w_mw - w_ms):.2f}")
        print(line)
        print(f"    top: {top}")
    layers(by, main_st, keep, pw, unit, a.top)
    gaps(keep, pw, unit)


def gaps(keep, pw, unit, min_ns=3_000, top=14):
    """GPU-idle gaps (no op on any stream) of >= min_ns, by the op that ended last before and the op that starts after."""
    by_pair = defaultdict(lambda: [0, 0])
    hist = defaultdict(int)
    end, last = None, None
    for s, e, st, n in keep:
        if end is not None and s > end:
            g = s - end
            for lo in (3_000, 10_000, 30_000, 100_000, 300_000, 1_000_000):
                if g >= lo:
                    b = lo
            if g >= min_ns:
                hist[b] += g
                k = by_pair[(fold(last), fold(n))]
                k[0] += 1
                k[1] += g
        if end is None or e > end:
            end, last = e, n
    print("GPU idle gaps >= 3 us by size (from): " + ", ".join(f">={b / 1e3:.0f}us {pw(t):.2f}" for b, t in sorted(hist.items())) + f" {unit}")
    for (x, y), (c, t) in sorted(by_pair.items(), key=lambda kv: -kv[1][1])[:top]:
        print(f"  {pw(t):6.2f} {unit} {c:7d} gaps  after {x}  ->  before {y}")


def layers(by, main_st, keep, pw, unit, top_n):
    """The main stream's per-layer cycle: the GPU-only chain (combine of layer l-1 .. doorbell of layer l) and the
    expert region (doorbell .. combine: VRAM hits, the CPU's results, the copy)."""
    m = by[main_st]
    bell = [i for i, x in enumerate(m) if "doorbell_publish" in x[3]]
    comb = [i for i, x in enumerate(m) if "combine_k10" in x[3]]
    if not bell or not comb:
        print("layers: no doorbell / combine kernels on the main stream")
        return
    others = union([(s, e) for s, e, st, n in keep if st != main_st and not SPIN.search(n)])
    starts = [x[0] for x in keep]
    # per region: when the last spin kernel (any stream) ended - the host's flag, i.e. the CPU's results - and when the
    # GPU work that started before it ended; the CPU bounds the region by the gap between the two
    cut = dict(n=0, spin_end=0, gpu_end=0, cpu_wait=0, post=0)
    reg = dict(n=0, span=0, work=0, spin=0, idle=0, side=0)
    chain = dict(n=0, span=0, idle=0)
    kreg, kchain = defaultdict(int), defaultdict(int)
    ci = 0
    prev_comb = None
    for b in bell:
        while ci < len(comb) and comb[ci] < b:
            prev_comb = comb[ci]
            ci += 1
        if ci == len(comb):
            break
        c = comb[ci]
        r0, r1 = m[b][1], m[c][0]
        if r1 - r0 > 2_000_000:   # not one layer's region (a window boundary or a stall)
            continue
        reg["n"] += 1
        reg["span"] += r1 - r0
        busy = 0
        for s, e, _, n in m[b + 1:c]:
            d = min(e, r1) - max(s, r0)
            if d <= 0:
                continue
            busy += d
            if SPIN.search(n):
                reg["spin"] += d
            else:
                reg["work"] += d
                kreg[fold(n)] += d
        reg["idle"] += (r1 - r0) - busy
        reg["side"] += inter(others, [[r0, r1]])
        k0 = bisect.bisect_left(starts, r0 - 300_000)
        spin_end = 0
        ops_in = []
        for s, e, st, n in keep[k0:bisect.bisect_left(starts, r1)]:
            if e <= r0:
                continue
            if SPIN.search(n):
                if e <= r1:
                    spin_end = max(spin_end, e)
            else:
                ops_in.append((s, e))
        if spin_end:
            gpu_end = max([min(e, spin_end) for s, e in ops_in if s < spin_end] or [r0])
            cut["n"] += 1
            cut["spin_end"] += spin_end - r0
            cut["gpu_end"] += gpu_end - r0
            cut["cpu_wait"] += max(0, spin_end - max(gpu_end, r0))
            cut["post"] += r1 - spin_end
        if prev_comb is not None and m[b][1] - m[prev_comb][0] < 2_000_000:
            g0, g1 = m[prev_comb][0], m[b][1]
            chain["n"] += 1
            chain["span"] += g1 - g0
            busy = 0
            for s, e, _, n in m[prev_comb:b + 1]:
                d = min(e, g1) - max(s, g0)
                if d > 0:
                    busy += d
                    kchain[fold(n)] += d
            chain["idle"] += (g1 - g0) - busy
    if reg["n"] == 0:
        print("layers: no doorbell -> combine regions found")
        return
    us = lambda ns, n: ns / 1e3 / max(n, 1)
    print(f"layers: {reg['n']} expert regions, {chain['n']} GPU chains (us a layer, mean)")
    print(f"  GPU chain (combine .. doorbell): {us(chain['span'], chain['n']):.1f} us, main idle in it "
          f"{us(chain['idle'], chain['n']):.1f}; total {pw(chain['span']):.2f} {unit}")
    print("    top: " + ", ".join(f"{n} {us(d, chain['n']):.1f}" for n, d in sorted(kchain.items(), key=lambda x: -x[1])[:top_n + 4]))
    print(f"  expert region (doorbell .. combine): {us(reg['span'], reg['n']):.1f} us = main work {us(reg['work'], reg['n']):.1f}"
          f" + spin {us(reg['spin'], reg['n']):.1f} + idle {us(reg['idle'], reg['n']):.1f}; other streams' work in it "
          f"{us(reg['side'], reg['n']):.1f}; total {pw(reg['span']):.2f} {unit}")
    print("    top: " + ", ".join(f"{n} {us(d, reg['n']):.1f}" for n, d in sorted(kreg.items(), key=lambda x: -x[1])[:top_n]))
    if cut["n"]:
        print(f"  in {cut['n']} regions with a spin: last spin ends at {us(cut['spin_end'], cut['n']):.1f} us, the GPU work "
              f"started before it ends at {us(cut['gpu_end'], cut['n']):.1f}; GPU idle waiting on the flag "
              f"{us(cut['cpu_wait'], cut['n']):.1f} us; flag -> combine {us(cut['post'], cut['n']):.1f} us")


if __name__ == "__main__":
    main()
