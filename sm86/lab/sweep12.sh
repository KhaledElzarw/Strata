#!/bin/bash
# Phase 2b: CPU expert pool task granularity (--pool-tasks; default 3 per thread = 48), interleaved.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep12 > runs/TAG
mkdir -p runs/id/sweep12 && cp runs/id/sweep1/ref.tsv* runs/id/sweep12/
E='exe=C:\src\Strata\build-sm86\strata.exe'
B="$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1;STRATA_EXP_MODE=9"
python idcheck.py sweep12 --reuse-ref \
  --cand "$B;args=--pool-tasks 96" \
  --cand "$B;args=--pool-tasks 192" \
  --cand "$B" \
  --cand "$B;args=--pool-tasks 64" \
  --cand "$B;args=--pool-tasks 128" \
  --cand "$B;args=--pool-tasks 384" \
  --cand "$B" \
  --cand "$B;args=--pool-tasks 96"
echo "exit=$?"
echo idle > runs/TAG
