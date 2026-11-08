#!/bin/bash
# gr_up9_kernel (STRATA_GR_UP9=n: unpack once per batch, warp_sum4, all loads up front): bit identity against the adopted
# read and cold-weight time per T, alternating with the UP_PL arm.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc15 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1"
P="$N;STRATA_GR_UP_PL=1"
python hcbench.py hc15 "$N" "$P" "$P;STRATA_GR_UP9=3" "$P;STRATA_GR_UP9=1" "$P" "$P;STRATA_GR_UP9=3" \
  "STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_UP9=1" > runs/hc/hc15.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
