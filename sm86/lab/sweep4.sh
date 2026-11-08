#!/bin/bash
# Phase 2: exact-stack speed screen on identical work (forced decode, pinned windows), interleaved repeats, + identity.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep4 > runs/TAG
mkdir -p runs/id/sweep4 && cp runs/id/sweep1/ref.tsv* runs/id/sweep4/
E='exe=C:\src\Strata\build-sm86\strata.exe'
K='STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1'
F='STRATA_FETCH_FORK=1'
P='STRATA_GRAPH_PRIO=1'
python idcheck.py sweep4 --reuse-ref \
  --cand "" \
  --cand "$E;$K;$F;$P" \
  --cand "$E;$K;$F" \
  --cand "$E;$K;$F;$P;args=--host-core sibling" \
  --cand "$E;$K;$F;$P;STRATA_FUSE_WAIT=2;STRATA_EXP_MODE=8;STRATA_FUSE_DECODE=1" \
  --cand "" \
  --cand "$E;$K;$F;$P" \
  --cand "$E;$K;$F" \
  --cand "$E;$K;$F;$P;args=--host-core sibling" \
  --cand "$E;$K;$F;$P;STRATA_FUSE_WAIT=2;STRATA_EXP_MODE=8;STRATA_FUSE_DECODE=1" \
  --cand ""
echo "exit=$?"
echo idle > runs/TAG
