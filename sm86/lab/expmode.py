"""Per-format gate/up and down times of the grouped native experts, mode 0 against the AMD layouts (native_expert_bench).

    python expmode.py runs/expmode.log

Input: the bench's "layer N gu/down G g T t | mode 0: ... gu X us ... down Y us ... | mode M: ... | bitwise equal" lines
under "== mode M G/T g t" headers.  Prints, per phase and format, the summed time over the layers of that format for
mode 0 and each other mode, per group shape; and the layers that were not bitwise equal (there must be none).
"""
import re
import sys
from collections import defaultdict

RE = re.compile(r"layer\s+(\d+) (\S+)\s*/(\S+)\s+G (\d+) T (\d+) \| mode 0: all\s+([\d.]+) us\s+gu\s+([\d.]+) us.*?down\s+([\d.]+) us"
                r".*?\| mode (\d+): all\s+([\d.]+) us\s+gu\s+([\d.]+) us.*?down\s+([\d.]+) us.*?\| (.*)$")


def main(path):
    acc = defaultdict(lambda: [0.0, 0.0, 0])   # (phase, fmt, shape, mode) -> [mode0 us, mode us, layers]
    bad = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = RE.search(line)
        if not m:
            continue
        lay, gu, dn, g, t = int(m[1]), m[2], m[3], m[4], m[5]
        mode = int(m[9])
        shape = f"G{g}T{t}"
        a = acc[("gu", gu, shape, mode)]
        a[0] += float(m[7]); a[1] += float(m[11]); a[2] += 1
        d = acc[("down", dn, shape, mode)]
        d[0] += float(m[8]); d[1] += float(m[12]); d[2] += 1
        if "bitwise equal" not in m[13]:
            bad.append((lay, mode, shape, m[13].strip()))
    for phase in ("gu", "down"):
        print(f"== {phase}: summed us over the format's layers (mode 0 -> mode M, ratio)")
        keys = sorted({(k[1], k[2]) for k in acc if k[0] == phase})
        modes = sorted({k[3] for k in acc if k[0] == phase})
        for fmt, shape in keys:
            cells = []
            for md in modes:
                v = acc.get((phase, fmt, shape, md))
                if v and v[2]:
                    cells.append(f"m{md} {v[0]:7.1f}->{v[1]:7.1f} ({v[1] / v[0]:.2f})")
            n = next(acc[(phase, fmt, shape, md)][2] for md in modes if (phase, fmt, shape, md) in acc)
            print(f"  {fmt:8s} {shape:7s} {n:2d} layers  " + "  ".join(cells))
    print("not bitwise equal:", bad if bad else "none")


if __name__ == "__main__":
    main(sys.argv[1])
