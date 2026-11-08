#!/bin/bash
# After the A/A check: the HC kernel bench (bits + cold time per variant), then the exact-switch sweep.
cd /d/Projects/local_ai/strata-lab || exit 2
echo hcbench > runs/TAG
python hcbench.py hc1 "" "STRATA_GR_DOWN_NW=4" "STRATA_GR_DOWN_TG=2" "STRATA_GR_UP_WIDE=1" "STRATA_GR_NORM_FAST=1" \
  "STRATA_HC_UPMIX=1" "STRATA_GR_DOWN_NW=4;STRATA_GR_UP_WIDE=1;STRATA_GR_NORM_FAST=1" "" > runs/hc/hc1.log 2>&1
echo "hcbench exit=$?"
tail -80 runs/hc/hc1.log
bash sweep1.sh > runs/id/sweep1.log 2>&1
echo "sweep exit=$?"
