#!/bin/bash
# After the cleanup (PF, UP9, UP320, ND86 removed; the resident read's final path only): identity and timing of the
# adopted stack (UP_PL + D87=8) against STRATA_GR_RES=1, and its phase profile.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc24 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;STRATA_GR_UP_PL=1;STRATA_GR_D87=8"
python hcbench.py hc24 "$N" "$N;STRATA_GR_RES=1" "$N;STRATA_GR_RES=1;STRATA_GR_RES_PROF=1" "$N" "$N;STRATA_GR_RES=1" \
  "STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1" --tmax 8 > runs/hc/hc24.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
