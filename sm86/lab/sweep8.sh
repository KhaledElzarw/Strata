#!/bin/bash
# Phase 2: mode 9 with a larger PCIe share (the MoE step waits on the CPU's share): forced-decode speed, interleaved.
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep8 > runs/TAG
mkdir -p runs/id/sweep8 && cp runs/id/sweep1/ref.tsv* runs/id/sweep8/
E='exe=C:\src\Strata\build-sm86\strata.exe'
B="$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1"
python idcheck.py sweep8 --reuse-ref \
  --cand "$B" \
  --cand "$B;args=--pcie-frac 0.4" \
  --cand "$B;STRATA_EXP_MODE=9;args=--pcie-frac 0.4" \
  --cand "$B;STRATA_EXP_MODE=9;args=--pcie-frac 0.5" \
  --cand "$B;STRATA_EXP_MODE=9;args=--pcie-frac 0.6" \
  --cand "$B;STRATA_EXP_MODE=9;args=--pcie-frac 0.6" \
  --cand "$B;STRATA_EXP_MODE=9;args=--pcie-frac 0.5" \
  --cand "$B;STRATA_EXP_MODE=9;args=--pcie-frac 0.4" \
  --cand "$B;args=--pcie-frac 0.4" \
  --cand "$B"
echo "exit=$?"
echo idle > runs/TAG
