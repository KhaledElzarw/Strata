#!/bin/bash
# Phase 2, step 4: exact-switch sweep on the prebuilt engine (plus the source build as an A/A), one reference, idcheck.py.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep1 > runs/TAG
python idcheck.py sweep1 \
  --cand "exe=C:\\src\\Strata\\build-sm86\\strata.exe" \
  --cand "STRATA_GR_DOWN_TG=2" \
  --cand "STRATA_GR_UP_WIDE=1" \
  --cand "STRATA_GR_NORM_FAST=1" \
  --cand "STRATA_HC_UPMIX=1" \
  --cand "STRATA_EXP_MODE=8" \
  --cand "STRATA_IQ_GATHER=1" \
  --cand "STRATA_MMVF_ROWS=1" \
  --cand "STRATA_ATTN_LANECELL=1" \
  --cand "STRATA_ATTN_MERGE_V2=1" \
  --cand "STRATA_TSUM=1" \
  --cand "STRATA_LFUSE=1" \
  --cand "STRATA_GDN_SPLIT=1" \
  --cand "STRATA_QFUSE=1" \
  --cand "STRATA_PLE_BATCH=1" \
  --cand "STRATA_SMALL_UNR=3" \
  --cand "STRATA_FUSE_WAIT=2" \
  --cand "STRATA_FUSE_DECODE=1" \
  --cand "STRATA_SH_STREAM=1" \
  --cand "STRATA_EXPERT_V2=1" \
  --cand ""
echo "exit=$?"
echo idle > runs/TAG
