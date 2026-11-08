#!/bin/bash
# Phase 2f: whole-engine identity of the three MoE-chain trims (design council "MoE step chain"): STRATA_DOORBELL_STORE=1
# (the doorbell's sequence stored, not incremented over PCIe), STRATA_FUSE_HITS=1 (the VRAM hits added inside the combine,
# CUDA), STRATA_ACTQ_SKIP=1 (the CPU's activation quantization skipped for tokens with no CPU expert), each and together;
# and the HC council's steps 1-2: STRATA_GR_UP320=1 (one-batch up), STRATA_GR_ND86=1 (norm + DOWN86 in one launch).
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep17 > runs/TAG
mkdir -p runs/id/sweep17 && cp runs/id/sweep1/ref.tsv* runs/id/sweep17/
E='exe=C:\src\Strata\build-sm86\strata.exe'
S="STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1;STRATA_EXP_MODE=9;STRATA_DECODE_TIMING=1"
N="$E;STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;$S;STRATA_EXP9_DOWN=42:10"
python idcheck.py sweep17 --reuse-ref \
  --cand "$N;STRATA_DOORBELL_STORE=1" \
  --cand "$N;STRATA_FUSE_HITS=1" \
  --cand "$N;STRATA_ACTQ_SKIP=1" \
  --cand "$N;STRATA_DOORBELL_STORE=1;STRATA_FUSE_HITS=1;STRATA_ACTQ_SKIP=1"   --cand "$N;STRATA_GR_UP320=1"   --cand "$N;STRATA_GR_ND86=1"   --cand "$N;STRATA_DOORBELL_STORE=1;STRATA_FUSE_HITS=1;STRATA_ACTQ_SKIP=1;STRATA_GR_UP320=1;STRATA_GR_ND86=1"
echo "exit=$?"
echo idle > runs/TAG
