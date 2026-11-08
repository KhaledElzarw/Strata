#!/bin/bash
# The cleanup build with the up loop unrolled only to T 4 (T 5..8 roll: no spill): RES=1 against the adopted stack, twice.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc25 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;STRATA_GR_UP_PL=1;STRATA_GR_D87=8"
python hcbench.py "${1:-hc25}" "$N" "$N;STRATA_GR_RES=1" "$N;STRATA_GR_RES=1;STRATA_GR_RES_PROF=1" "$N" "$N;STRATA_GR_RES=1" --tmax 8 > "runs/hc/${1:-hc25}.log" 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
