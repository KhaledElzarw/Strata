"""Summarize native_expert_bench logs per gate/up and down format: the reference mode's and the test mode's
gate/up, down and whole-step times (us, summed over the layers of each format) and whether every layer was bitwise equal.

    python expsum.py runs/exp/m10-vs0-g24t1.log [more logs ...]
"""
import re
import sys
from collections import defaultdict

RE = re.compile(r"layer\s+(\d+)\s+(\S+)\s*/\s*(\S+)\s+G (\d+) T (\d+) \| mode (\d+): all\s+([\d.]+) us\s+gu\s+([\d.]+) us.*?"
                r"down\s+([\d.]+) us.*?\| mode (\d+): all\s+([\d.]+) us\s+gu\s+([\d.]+) us.*?down\s+([\d.]+) us.*?\| (.+)$")

for path in sys.argv[1:]:
    gu = defaultdict(lambda: [0, 0.0, 0.0, 0.0, 0.0, 0])
    dn = defaultdict(lambda: [0, 0.0, 0.0, 0])
    tot = [0.0, 0.0]
    modes = None
    bad = []
    for line in open(path, encoding="utf-8", errors="replace"):
        m = RE.search(line)
        if not m:
            continue
        l, tg, td = int(m[1]), m[2], m[3]
        mr, ar, gr, dr, mt, at, gt, dt, verdict = int(m[6]), float(m[7]), float(m[8]), float(m[9]), int(m[10]), float(m[11]), float(m[12]), float(m[13]), m[14].strip()
        modes = (mr, mt)
        g = gu[tg]
        g[0] += 1; g[1] += gr; g[2] += gt; g[3] += ar; g[4] += at
        if verdict != "bitwise equal":
            g[5] += 1; bad.append(l)
        d = dn[td]
        d[0] += 1; d[1] += dr; d[2] += dt
        tot[0] += ar; tot[1] += at
    print(f"== {path}: mode {modes[0] if modes else '?'} (ref) vs {modes[1] if modes else '?'}")
    for k, g in sorted(gu.items()):
        print(f"  gate/up {k:8s} {g[0]:2d} layers  gu {g[1]:7.1f} -> {g[2]:7.1f} us ({g[2] / g[1]:.3f})  all {g[3]:7.1f} -> {g[4]:7.1f} ({g[4] / g[3]:.3f})"
              + (f"  DIFFERS on {g[5]}" if g[5] else ""))
    for k, d in sorted(dn.items()):
        print(f"  down    {k:8s} {d[0]:2d} layers  down {d[1]:7.1f} -> {d[2]:7.1f} us ({d[2] / d[1]:.3f})")
    if tot[0]:
        print(f"  all layers: {tot[0]:.1f} -> {tot[1]:.1f} us ({tot[1] / tot[0]:.3f}); differing layers: {bad if bad else 'none'}")
