#!/bin/bash
# Phase 2e: whole-engine identity on the build with the L1 fixes of decisions 0002/0003 (ready flag per batch, mode-10
# gate/up = mode 0's): the new base N (+ the adopted Q2_0 down kernel), + POOL_DAG (both together: Codex Sol's open
# point), and two existing exact sync switches: STRATA_FUSE_WAIT=2 (the plan's wait folded into its copy) and
# STRATA_VERIFY_DEVICE_PLAN=1 (all-resident layers planned on the device).
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep16 > runs/TAG
mkdir -p runs/id/sweep16 && cp runs/id/sweep1/ref.tsv* runs/id/sweep16/
E='exe=C:\src\Strata\build-sm86\strata.exe'
S="STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1;STRATA_EXP_MODE=9;STRATA_DECODE_TIMING=1"
N="$E;STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;$S;STRATA_EXP9_DOWN=42:10"
python idcheck.py sweep16 --reuse-ref \
  --cand "$N" \
  --cand "$N;STRATA_POOL_DAG=1" \
  --cand "$N;STRATA_FUSE_WAIT=2" \
  --cand "$N;STRATA_VERIFY_DEVICE_PLAN=1"
echo "exit=$?"
echo idle > runs/TAG
