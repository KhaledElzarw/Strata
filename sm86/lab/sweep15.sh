#!/bin/bash
# Phase 2d: whole-engine identity after the L1 review fixes (HC), plus the CPU pool DAG (decision 0003) and the expert
# gate/up planes kernel (mode 10, decision 0002) on every gate/up format.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep15 > runs/TAG
mkdir -p runs/id/sweep15 && cp runs/id/sweep1/ref.tsv* runs/id/sweep15/
E='exe=C:\src\Strata\build-sm86\strata.exe'
S="STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1;STRATA_EXP_MODE=9;STRATA_DECODE_TIMING=1"
N="$E;STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;$S"
python idcheck.py sweep15 --reuse-ref \
  --cand "$N" \
  --cand "$N;STRATA_POOL_DAG=1" \
  --cand "$N;STRATA_EXP9_DOWN=42:10" \
  --cand "$N;STRATA_POOL_DAG=1;args=--pool-tasks 96"
echo "exit=$?"
echo idle > runs/TAG
