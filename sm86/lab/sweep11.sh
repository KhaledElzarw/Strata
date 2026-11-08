#!/bin/bash
# Phase 2b: CPU expert pool on the SMT siblings too (the share looks compute-bound: large pages gave +0.7%), interleaved.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep11 > runs/TAG
mkdir -p runs/id/sweep11 && cp runs/id/sweep1/ref.tsv* runs/id/sweep11/
E='exe=C:\src\Strata\build-sm86\strata.exe'
B="$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1;STRATA_EXP_MODE=9"
python idcheck.py sweep11 --reuse-ref \
  --cand "$B" \
  --cand "$B;args=--pool-cores 2-31" \
  --cand "$B;args=--pool-cores 1-31" \
  --cand "$B;args=--pool-tasks 96" \
  --cand "$B;args=--pool-cores 2-31" \
  --cand "$B"
echo "exit=$?"
echo idle > runs/TAG
