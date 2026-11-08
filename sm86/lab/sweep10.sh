#!/bin/bash
# Phase 2b: large pages for the CPU expert arena (SeLockMemoryPrivilege granted 2026-11-08), exact stack, interleaved.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep10 > runs/TAG
mkdir -p runs/id/sweep10 && cp runs/id/sweep1/ref.tsv* runs/id/sweep10/
E='exe=C:\src\Strata\build-sm86\strata.exe'
B="$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1;STRATA_EXP_MODE=9"
python idcheck.py sweep10 --reuse-ref \
  --cand "$B;STRATA_NO_LARGEPAGES=1" \
  --cand "$B" \
  --cand "$B" \
  --cand "$B;STRATA_NO_LARGEPAGES=1"
echo "exit=$?"
echo idle > runs/TAG
