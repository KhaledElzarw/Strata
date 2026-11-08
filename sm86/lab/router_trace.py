"""The router chain of every MoE layer in an Nsight Systems cuda_gpu_trace CSV (issue #3, decision 0006).

    python router_trace.py runs/nsys/q3_cuda_gpu_trace.csv > runs/nsys/q3_router.txt

A chain is, on one stream: the router GEMV (bf16_f32_mmvf_*kernel, grid 512), the top-10 (route_multi / route) and the
doorbell (doorbell_publish_res_kernel), or the fused top-10 + doorbell (route_bell, STRATA_ROUTE_BELL).  Prints, in us:
the gaps between the three kernels, every BF16 GEMV's duration by grid and token count (the template's NT; 1 for the
one-token kernel), and the top-10 and doorbell durations by the chain's token count.
"""
import csv
import re
import statistics as st
import sys
from collections import defaultdict

TOK = re.compile(r"mmvf_(?:multi_|rows_)?kernel<\(int\)\d+(?:, \(int\)(\d+))?")


def ntok(name):
    m = TOK.search(name)
    return int(m.group(1)) if m and m.group(1) else 1


def stats(v):
    v = sorted(v)
    return (f"n {len(v):6d}  mean {st.mean(v):6.2f}  median {v[len(v) // 2]:6.2f}  p10 {v[len(v) // 10]:6.2f}  "
            f"p90 {v[9 * len(v) // 10]:6.2f}")


def main(path):
    gemv = defaultdict(list)                 # (grid, kernel, NT) -> durations
    by_nt = defaultdict(lambda: defaultdict(list))
    gaps = []
    last = {}
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        r = csv.reader(f)
        h = next(r)
        iS, iD, iG, iSt, iN = (h.index(k) for k in ("Start (ns)", "Duration (ns)", "GrdX", "Strm", "Name"))
        for row in r:
            name = row[iN]
            is_gemv = "mmvf" in name
            is_route = "route_multi" in name or "::route(" in name
            is_bell = "doorbell_publish_res" in name
            is_fused = "route_bell" in name
            if not (is_gemv or is_route or is_bell or is_fused):
                continue
            s, d, strm, grid = int(row[iS]), int(row[iD]), row[iSt], row[iG]
            if is_gemv:
                kind = "rows" if "rows_kernel" in name else "multi" if "multi_kernel" in name else "single"
                gemv[(int(grid or 0), kind, ntok(name))].append(d / 1e3)
            L = last.setdefault(strm, {})
            if is_gemv and grid == "512":
                L.clear()
                L["gemv"] = (s, s + d, ntok(name))
            elif is_route and "gemv" in L:
                L["route"] = (s, s + d)
            elif is_fused and "gemv" in L:
                g = L.pop("gemv")
                by_nt[g[2]]["fused"].append(d / 1e3)
                gaps.append(((s - g[1]) / 1e3, None, None, d / 1e3, (s + d - g[1]) / 1e3, (g[1] - g[0]) / 1e3))
            elif is_bell and "gemv" in L and "route" in L:
                g, ro = L.pop("gemv"), L.pop("route")
                by_nt[g[2]]["top-10"].append((ro[1] - ro[0]) / 1e3)
                by_nt[g[2]]["doorbell"].append(d / 1e3)
                gaps.append(((ro[0] - g[1]) / 1e3, (ro[1] - ro[0]) / 1e3, (s - ro[1]) / 1e3, d / 1e3,
                             (s + d - g[1]) / 1e3, (g[1] - g[0]) / 1e3))
    print(f"{path}\n{len(gaps)} router chains")
    for k, n in enumerate(["gap gemv -> next", "top-10", "gap top-10 -> doorbell", "doorbell (or fused)",
                           "gemv end -> doorbell end", "router gemv"]):
        v = [x[k] for x in gaps if x[k] is not None]
        if v:
            print(f"  {n:26s} {stats(v)}")
    print("\nBF16 GEMV by grid, kernel and token count (us; sum in ms over the trace)")
    for (grid, kind, nt), v in sorted(gemv.items()):
        if len(v) >= 50:
            print(f"  grid {grid:6d} {kind:6s} T {nt}  {stats(v)}  sum {sum(v) / 1e3:7.1f}")
    print("\ntop-10 / doorbell / fused by the chain's token count (us)")
    for nt in sorted(by_nt):
        for k in ("top-10", "doorbell", "fused"):
            if by_nt[nt][k]:
                print(f"  T {nt} {k:8s} {stats(by_nt[nt][k])}")


if __name__ == "__main__":
    main(sys.argv[1])
