#!/bin/bash
# RES after the norm CTAs' W_up moved behind barrier 1 and the up phase took gr_up9's sums: profile (+16) and timing.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc20 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;STRATA_GR_UP_PL=1;STRATA_GR_D87=8"
python hcbench.py hc20 "$N" "$N;STRATA_GR_RES=18" "$N;STRATA_GR_RES=17" "$N;STRATA_GR_RES=2" "$N;STRATA_GR_RES=1" \
  "$N;STRATA_GR_RES=2" "$N" --tmax 8 > runs/hc/hc20.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
