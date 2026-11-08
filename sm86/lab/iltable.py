"""The 3090's interleaved-MMVQ rows table from several `mmvq_il_parity --bench --emit-table` runs.

    python iltable.py runs/mmvq-il-sm86.log runs/mmvq-il-sm86-r2.log runs/mmvq-il-sm86-r3.log

Per (type, shape, T) each arm's time is the median over the runs.  Per cell (type, columns, n_out class) the rows count
1/2/4 whose WORST ratio to native_mmvq over the cell's shapes is the best is taken when that ratio is under 0.97, else 0
(mmvq_il_parity's own rule), but only over the shapes this model runs with that type (SC117 IQ3_XXS: attn_k/v 512,
shared-expert gate/up 640, attn_gate 6144, attn_qkv 10240, attn_q 12288, the Q5_K head 248320 and the drafter's Q5_K
head 106299).  A class with none of the model's shapes takes the plain rule over every measured shape (it never runs
here).  Every rows count is bitwise native_mmvq's output (the same tool's parity check), so the table is only speed.
"""
import re
import statistics
import sys
from collections import defaultdict

NAMES = {23: "IQ4_XS", 12: "Q4_K", 13: "Q5_K", 14: "Q6_K", 11: "Q3_K"}
TYPE_OF = {v: k for k, v in NAMES.items()}
MODEL = {23: {512, 640, 6144, 10240, 12288}, 12: {512, 640, 6144, 10240, 12288}, 14: {512, 640, 6144, 10240, 12288},
         13: {512, 640, 6144, 10240, 248320, 106299}, 11: set()}
RE = re.compile(r"BENCH (\S+) .*?(\d+)x(\d+)\s.*?T=(\d) \S+\s+multi ([\d.]+) us \| il rows1 ([\d.]+) rows2 ([\d.]+) rows4 ([\d.]+)")


def cls_of(n):
    return 0 if n < 2048 else 1 if n < 4096 else 2 if n < 8192 else 3 if n < 12288 else 4


def main(paths):
    t = defaultdict(list)                       # (type, n_out, T) -> [(ref, r1, r2, r4)] per run
    for p in paths:
        for m in RE.finditer(open(p, encoding="utf-8", errors="replace").read()):
            ty = TYPE_OF.get(m[1])
            if ty is None:
                continue
            t[(ty, int(m[3]), int(m[4]))].append(tuple(float(m[i]) for i in range(5, 9)))
    med = {k: tuple(statistics.median(x[i] for x in v) for i in range(4)) for k, v in t.items()}
    runs = {len(v) for v in t.values()}
    print(f"// {len(paths)} runs, {len(med)} cells, runs per cell {sorted(runs)}")

    def pick(ty, nc, c, prev, only_model):
        best, best_w, any_ = 0, 1e9, False
        for ri, r in ((1, 1), (2, 2), (3, 4)):
            worst, have = 0.0, False
            for (ty2, n, T), v in med.items():
                if ty2 != ty or T != nc or cls_of(n) != c or (only_model and n not in MODEL[ty]):
                    continue
                have = True
                worst = max(worst, v[ri] / v[0])
            any_ = any_ or have
            if have and worst < best_w:
                best_w, best = worst, r
        if not any_:
            return prev, None
        return (best if best_w < 0.97 else 0), best_w

    def row(ty, nc, prev=0):
        out, notes = [], []
        for c in range(5):
            has_model = any(cls_of(n) == c for n in MODEL[ty])
            v, w = pick(ty, nc, c, prev, has_model)
            prev = v
            out.append(v)
            notes.append("-" if w is None else f"{w:.2f}")
        return out, notes

    for title, cols in (("2-4 columns (kIlRows)", (2, 3, 4)), ("5-8 columns (kIlRows58; rows 4 runs as 2 there)", (5, 6, 7, 8))):
        print(f"// {title}")
        for ty in (23, 12, 13, 14, 11):
            rows = [row(ty, nc) for nc in cols]
            body = ", ".join("{" + ", ".join(map(str, r)) + "}" for r, _ in rows)
            print(f"    {{{ty}, {{{body}}}}},   // {NAMES[ty]}  worst ratios " + " | ".join(" ".join(n) for _, n in rows))
    print("// one column (kIl1Rows)")
    for ty in (23, 12, 13, 14, 11):
        r, n = row(ty, 1)
        print(f"    {{{ty}, {{{', '.join(map(str, r))}}}}},   // {NAMES[ty]}  worst ratios {' '.join(n)}")
    if len(paths) > 1:   # run-to-run spread of the arms that matter
        print("// spread (max/min over runs) of the model's cells, worst 8:")
        sp = []
        for (ty, n, T), v in t.items():
            if n in MODEL[ty] and len(v) > 1:
                for i, nm in enumerate(("multi", "rows1", "rows2", "rows4")):
                    xs = [x[i] for x in v]
                    sp.append((max(xs) / min(xs), f"{NAMES[ty]} n_out {n} T={T} {nm}: {xs}"))
        for s, txt in sorted(sp, reverse=True)[:8]:
            print(f"//   {s:.2f}  {txt}")


if __name__ == "__main__":
    main(sys.argv[1:])
