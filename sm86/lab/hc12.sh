#!/bin/bash
# HC council step 1-2 (decision 0004): gr_up320 (STRATA_GR_UP320=1) and the fused norm + DOWN86 launch (STRATA_GR_ND86=1),
# bit identity against the adopted read and cold-weight time per T; plus the opt-in persistent read's time (tier B,
# STRATA_HC_PERSIST=1, the bench's persist lines).
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc12 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1"
python hcbench.py hc12 "$N" "$N;STRATA_GR_UP320=1" "$N;STRATA_GR_ND86=1" "$N;STRATA_GR_UP320=1;STRATA_GR_ND86=1" \
  "STRATA_NO_MULTI_GR=1;$N;STRATA_GR_UP320=1;STRATA_GR_ND86=1" "$N;STRATA_HC_PERSIST=1" > runs/hc/hc12.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
