#!/bin/bash
# RES mode 3 (counters, the norm loads first, W_up after them) and + 32 (norm CTAs W_up after their down loop), profiles.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc21 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;STRATA_GR_UP_PL=1;STRATA_GR_D87=8"
python hcbench.py hc21 "$N" "$N;STRATA_GR_RES=3" "$N;STRATA_GR_RES=19" "$N;STRATA_GR_RES=35" "$N;STRATA_GR_RES=51" \
  "$N;STRATA_GR_RES=2" "$N" --tmax 8 > runs/hc/hc21.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
