#!/bin/bash
# gr_down87_kernel (STRATA_GR_D87=8: DOWN86 with copy addresses worked out once; =4: 4 lanes a block, 160 blocks) and the
# plain-read floor (STRATA_BENCH_BW=1 probe lines): bit identity against the adopted read and cold-weight time per T.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc16 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1"
P="$N;STRATA_GR_UP_PL=1"
python hcbench.py hc16 "$N" "$P;STRATA_BENCH_BW=1" "$P;STRATA_GR_D87=8" "$P;STRATA_GR_D87=4" "$P" "$P;STRATA_GR_D87=4" \
  "$P;STRATA_GR_D87=8" > runs/hc/hc16.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
