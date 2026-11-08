#!/bin/bash
# Phase 2: CPU-side exact switches on the exact stack (the MoE step waits on the CPU share): forced decode, interleaved.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep9 > runs/TAG
mkdir -p runs/id/sweep9 && cp runs/id/sweep1/ref.tsv* runs/id/sweep9/
E='exe=C:\src\Strata\build-sm86\strata.exe'
B="$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1;STRATA_EXP_MODE=9"
python idcheck.py sweep9 --reuse-ref \
  --cand "$B" \
  --cand "$B;STRATA_IQ_GATHER=1" \
  --cand "$B;STRATA_IQ_GATHER=1" \
  --cand "$B"
echo "exit=$?"
echo idle > runs/TAG
