#!/bin/bash
# After the council L2 fixes: the adopted read, RES cooperative and plain, and the probes (STRATA_BENCH_BW=1); bits + time.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc29 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;STRATA_GR_UP_PL=1;STRATA_GR_D87=8"
python hcbench.py hc29 "$N" "$N;STRATA_GR_RES=1" "$N;STRATA_GR_RES=1;STRATA_GR_RES_COOP=0" "$N;STRATA_GR_RES=1" "$N;STRATA_GR_RES=1;STRATA_GR_RES_COOP=0" "$N;STRATA_BENCH_BW=1" --tmax 8 > runs/hc/hc29.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
