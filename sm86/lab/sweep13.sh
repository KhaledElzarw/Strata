#!/bin/bash
# Phase 2b: is the CPU expert share compute- or memory-bound?  Pool size and CCD placement, with decode timing lines.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep13 > runs/TAG
mkdir -p runs/id/sweep13 && cp runs/id/sweep1/ref.tsv* runs/id/sweep13/
E='exe=C:\src\Strata\build-sm86\strata.exe'
B="$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1;STRATA_EXP_MODE=9;STRATA_DECODE_TIMING=1"
python idcheck.py sweep13 --reuse-ref \
  --cand "$B" \
  --cand "$B;args=--pool-workers 11" \
  --cand "$B;args=--pool-workers 7" \
  --cand "$B;args=--pool-cores 2,4,6,8,10,12,14" \
  --cand "$B;args=--pool-cores 16,18,20,22,24,26,28" \
  --cand "$B;args=--host-core last"
echo "exit=$?"
echo idle > runs/TAG
