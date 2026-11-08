#!/bin/bash
# RES=75 (counters, norm CTAs' W_up after the election, unrolled up) against + 128 (W_up's second batch after the ring's last tile).
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc23 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;STRATA_GR_UP_PL=1;STRATA_GR_D87=8"
python hcbench.py hc23 "$N" "$N;STRATA_GR_RES=75" "$N;STRATA_GR_RES=203" "$N;STRATA_GR_RES=219" "$N;STRATA_GR_RES=139" \
  "$N;STRATA_GR_RES=75" "$N;STRATA_GR_RES=203" "$N" --tmax 8 > runs/hc/hc23.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
