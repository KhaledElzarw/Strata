#!/bin/bash
# STRATA_GR_RES phases: the profile (+16) of RES=1, RES=1 with W_up after barrier 1 (+4), RES=2 (election), RES=2+4.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc19 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;STRATA_GR_UP_PL=1;STRATA_GR_D87=8"
python hcbench.py hc19 "$N" "$N;STRATA_GR_RES=17" "$N;STRATA_GR_RES=21" "$N;STRATA_GR_RES=18" "$N;STRATA_GR_RES=22" \
  "$N;STRATA_GR_RES=5" "$N;STRATA_GR_RES=6" "$N;STRATA_GR_RES=2" --tmax 8 > runs/hc/hc19.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
