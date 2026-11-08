#!/bin/bash
# Phase 2: the 3090's MMVQ tables (STRATA_MMVQ_IL_3090=1) on the exact stack: identity + forced-decode speed, interleaved.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep5 > runs/TAG
mkdir -p runs/id/sweep5 && cp runs/id/sweep1/ref.tsv* runs/id/sweep5/
E='exe=C:\src\Strata\build-sm86\strata.exe'
S='STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1'
I='STRATA_MMVQ_IL_3090=1'
python idcheck.py sweep5 --reuse-ref \
  --cand "" \
  --cand "$E;$S" \
  --cand "$E;$S;$I" \
  --cand "" \
  --cand "$E;$S;$I" \
  --cand "$E;$S" \
  --cand ""
echo "exit=$?"
echo idle > runs/TAG
