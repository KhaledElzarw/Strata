#!/bin/bash
# Phase 2: STRATA_EXP_MODE=9 (expert layout per format and phase) on the exact stack: identity + forced-decode speed.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep7 > runs/TAG
mkdir -p runs/id/sweep7 && cp runs/id/sweep1/ref.tsv* runs/id/sweep7/
E='exe=C:\src\Strata\build-sm86\strata.exe'
B="$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1"
python idcheck.py sweep7 --reuse-ref \
  --cand "" \
  --cand "$B" \
  --cand "$B;STRATA_EXP_MODE=9" \
  --cand "$B;STRATA_EXP_MODE=9" \
  --cand "$B" \
  --cand ""
echo "exit=$?"
echo idle > runs/TAG
