#!/bin/bash
# up75 bank-conflict-free shared layout (STRATA_GR_UP_PL=1): bit identity against the adopted read and cold-weight time
# per T, alternating arms to see the noise.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hc13 > runs/TAG
export PATH="/c/src/Strata/engine:/c/src/Strata/.venv/Lib/site-packages/nvidia/cu13/bin/x86_64:$PATH"
N="STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1"
python hcbench.py hc13 "$N" "$N;STRATA_GR_UP_PL=1" "$N" "$N;STRATA_GR_UP_PL=1" > runs/hc/hc13.log 2>&1
echo "hcbench exit $?"
echo idle > runs/TAG
