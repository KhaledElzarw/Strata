#!/bin/bash
# After the L1 review fixes (decision 0001): HC bit identity of every arm against the current stack, and the two
# reproductions Codex Sol gave (both must now exit 0).
cd /d/Projects/local_ai/strata-lab || exit 2
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
B=/c/src/Strata/build-sm86/fused_gr_bench.exe
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1"
python hcbench.py hc11 "STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1" "$N" "$N;STRATA_GR_D86_S=4" \
  "STRATA_NO_MULTI_GR=1;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1" "STRATA_NO_MULTI_GR=1;$N" \
  "STRATA_NO_MULTI_GR=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=4;STRATA_GR_UP8=0" > runs/hc/hc11.log 2>&1
echo "hcbench exit $?"
echo "== Sol P1 repro (was: illegal memory access)"
STRATA_HC_SPLIT=2 STRATA_GR_UP_WIDE=1 STRATA_GR_UP_HYB=4 STRATA_NO_MULTI_GR=1 STRATA_GR_UP8=0 "$B" 1 4 4 > runs/hc/solp1.log 2>&1
echo "exit $?"; tail -2 runs/hc/solp1.log
echo "== Sol P2 repro (was: invalid argument), 64 KiB card emulated"
STRATA_HC_SPLIT=2 STRATA_EMULATE_CC=75 STRATA_GR_DOWN_TG=0 STRATA_GR_DOWN86=1 STRATA_GR_D86_S=4 "$B" 1 5 5 > runs/hc/solp2.log 2>&1
echo "exit $?"; tail -2 runs/hc/solp2.log
echo "== P2 control: the same with DOWN82"
STRATA_HC_SPLIT=2 STRATA_EMULATE_CC=75 STRATA_GR_DOWN_TG=0 STRATA_GR_DOWN82=1 "$B" 1 5 5 > runs/hc/solp2c.log 2>&1
echo "exit $?"
python - <<'PY'
import re
h = {}
for f in ("solp2", "solp2c"):
    t = open(f"runs/hc/{f}.log").read()
    h[f] = re.findall(r"T (\d+) apply (\d+) inject (\d+) \|.*\| hash ([0-9a-f]+)", t)
print("P2 repro hashes equal to DOWN82 control:", h["solp2"] == h["solp2c"] and len(h["solp2"]) > 0, len(h["solp2"]), "cells")
PY
