#!/bin/bash
# DOWN86 ring depth: STRATA_GR_D86_S=4 (3 tiles in flight) against the default 3, on the UP_PL stack; D87=8 again.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc17 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1"
P="$N;STRATA_GR_UP_PL=1"
python hcbench.py hc17 "$P" "$P;STRATA_GR_D86_S=4" "$P;STRATA_GR_D87=8" "$P;STRATA_GR_D86_S=4" "$P" > runs/hc/hc17.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
