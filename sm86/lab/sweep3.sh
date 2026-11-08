#!/bin/bash
# Phase 2: STRATA_FETCH_FORK (the PCIe share's copy beside the VRAM experts), whole-engine bit identity vs the prebuilt reference.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep3 > runs/TAG
mkdir -p runs/id/sweep3 && cp runs/id/sweep1/ref.tsv* runs/id/sweep3/
E='exe=C:\src\Strata\build-sm86\strata.exe'
python idcheck.py sweep3 --reuse-ref \
  --cand "$E;STRATA_FETCH_FORK=1" \
  --cand "$E;STRATA_FETCH_FORK=1;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1" \
  --cand "$E;STRATA_FETCH_FORK=1;STRATA_FETCH_FORK_GRID=16" \
  --cand ""
echo "exit=$?"
echo idle > runs/TAG
