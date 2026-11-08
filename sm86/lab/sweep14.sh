#!/bin/bash
# Phase 2c: whole-engine identity of the HC kernels chosen by design council 0001 (UP_HYB, XN, DOWN86), plus pool-tasks 96.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep14 > runs/TAG
mkdir -p runs/id/sweep14 && cp runs/id/sweep1/ref.tsv* runs/id/sweep14/
E='exe=C:\src\Strata\build-sm86\strata.exe'
S="STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1;STRATA_EXP_MODE=9;STRATA_DECODE_TIMING=1"
B="$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;$S"
N="$E;STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;$S"
python idcheck.py sweep14 --reuse-ref \
  --cand "$B" \
  --cand "$N" \
  --cand "$N;args=--pool-tasks 96"
echo "exit=$?"
echo idle > runs/TAG
