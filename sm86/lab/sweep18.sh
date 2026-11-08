#!/bin/bash
# Whole-engine identity (forced-text head logits) of the tier-A candidates: the three MoE-chain trims
# (STRATA_DOORBELL_STORE, STRATA_FUSE_HITS, STRATA_ACTQ_SKIP), the up75 conflict-free layout (STRATA_GR_UP_PL=1),
# DOWN87 with precomputed copy addresses (STRATA_GR_D87=8), each and all together.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep18 > runs/TAG
mkdir -p runs/id/sweep18 && cp runs/id/sweep1/ref.tsv* runs/id/sweep18/
E='exe=C:\src\Strata\build-sm86\strata.exe'
S="STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1;STRATA_EXP_MODE=9;STRATA_DECODE_TIMING=1"
N="$E;STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;$S;STRATA_EXP9_DOWN=42:10"
python idcheck.py sweep18 --reuse-ref \
  --cand "$N;STRATA_DOORBELL_STORE=1" \
  --cand "$N;STRATA_FUSE_HITS=1" \
  --cand "$N;STRATA_ACTQ_SKIP=1" \
  --cand "$N;STRATA_GR_UP_PL=1" \
  --cand "$N;STRATA_GR_D87=8" \
  --cand "$N;STRATA_DOORBELL_STORE=1;STRATA_FUSE_HITS=1;STRATA_ACTQ_SKIP=1;STRATA_GR_UP_PL=1;STRATA_GR_D87=8"
echo "exit=$?"
echo idle > runs/TAG
