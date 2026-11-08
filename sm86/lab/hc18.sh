#!/bin/bash
# STRATA_GR_RES=1 (one resident kernel, design council round 2) against the adopted stack (UP_PL + D87=8), and the
# structure probe (STRATA_BENCH_BW=1: the plain-read floor and RES probe T 3/4/8, hold 1/0).
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc18 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;STRATA_GR_UP_PL=1;STRATA_GR_D87=8"
python hcbench.py hc18 "$N" "$N;STRATA_GR_RES=1" "$N;STRATA_BENCH_BW=1" "$N;STRATA_GR_RES=1" "$N" > runs/hc/hc18.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
