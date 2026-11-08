"""Window-weighted averages of Strata's per-request decode lines (STRATA_DECODE_TIMING / STRATA_VERIFY_PROFILE).

    python profsum.py runs/ab/logs/prof4-base-r0.engine.log [more logs ...]

Per log: ms/window, verify, GPU-reach wait, draft (decode timing) and the GPU stage split (GDN + QSA summed per stage name).
"""
import re
import sys
from collections import defaultdict

RE_T = re.compile(r"(\d+) windows, avg T ([\d.]+), ([\d.]+) tokens/window, ([\d.]+) ms/window.*?verify ([\d.]+) "
                  r"\(GPU-reach wait ([\d.]+) \+ per-layer host ([\d.]+).*?draft ([\d.]+)")
RE_S = re.compile(r"decode GPU stages \(ms/window\): (.*) \| total ([\d.]+) ms/window over (\d+) windows")
RE_KV = re.compile(r"([a-zA-Z0-9+/()\-][a-zA-Z0-9+/() \-]*?) ([\d.]+)(?=\s|$)")


def summarize(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    tw = 0
    acc = defaultdict(float)
    for m in RE_T.finditer(text):
        n = int(m[1])
        tw += n
        for k, i in (("T", 2), ("tok/win", 3), ("ms/window", 4), ("verify", 5), ("gpu-reach wait", 6), ("per-layer host", 7), ("draft", 8)):
            acc[k] += float(m[i]) * n
    sw = 0
    st = defaultdict(float)
    for m in RE_S.finditer(text):
        n = int(m[3])
        sw += n
        st["TOTAL"] += float(m[2]) * n
        for part in m[1].split("|"):
            body = part.split(":", 1)[1] if ":" in part else part
            for k, v in RE_KV.findall(body):
                k = k.strip()
                if k.startswith("hc"):
                    k = "hc " + k.split()[-1]          # hc0/hc1 norm/down/up -> hc norm/down/up
                st[k] += float(v) * n
    print(f"== {path}")
    if tw:
        print("  " + "  ".join(f"{k} {acc[k] / tw:.2f}" for k in acc) + f"  ({tw} windows)")
    if sw:
        items = sorted(((k, v / sw) for k, v in st.items()), key=lambda x: -x[1])
        print("  stages: " + "  ".join(f"{k} {v:.2f}" for k, v in items))


if __name__ == "__main__":
    for p in sys.argv[1:]:
        summarize(p)
