#!/bin/bash
# RES mode 3: the norm CTAs' W_up after the down loop (+32) or after the election (+64); the up's token loop unrolled (+8).
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc22 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;STRATA_GR_UP_PL=1;STRATA_GR_D87=8"
python hcbench.py hc22 "$N" "$N;STRATA_GR_RES=35" "$N;STRATA_GR_RES=67" "$N;STRATA_GR_RES=43" "$N;STRATA_GR_RES=75" \
  "$N;STRATA_GR_RES=91" "$N;STRATA_GR_RES=35" "$N;STRATA_GR_RES=75" "$N" --tmax 8 > runs/hc/hc22.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
