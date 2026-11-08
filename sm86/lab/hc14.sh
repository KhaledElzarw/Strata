#!/bin/bash
# L2 prefetch across the read's phase boundaries (STRATA_GR_PF mask, loads only): bit identity against the adopted read
# and cold-weight time per T.  1 up75 batch 1, 2 norm -> W_down tiles, 4 down86 own share, 8 down86 -> W_up half, 16 sectors.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc14 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1"
P="$N;STRATA_GR_UP_PL=1"
python hcbench.py hc14 "$N" "$P" "$P;STRATA_GR_PF=1" "$P;STRATA_GR_PF=2" "$P;STRATA_GR_PF=4" "$P;STRATA_GR_PF=8" \
  "$P;STRATA_GR_PF=15" "$P;STRATA_GR_PF=31" "$P;STRATA_GR_PF=6" "$P;STRATA_GR_PF=10;STRATA_GR_PF_UH=4" "$P" > runs/hc/hc14.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
