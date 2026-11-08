#!/bin/bash
# Phase 2: tier B / C speed screens on the exact stack (forced decode, identical work; DIFF is expected for B and C).
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep6 > runs/TAG
mkdir -p runs/id/sweep6 && cp runs/id/sweep1/ref.tsv* runs/id/sweep6/
E='exe=C:\src\Strata\build-sm86\strata.exe'
B="$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1"
NF="$E;STRATA_GR_DOWN82=1;STRATA_GR_UP_WIDE=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1"
python idcheck.py sweep6 --reuse-ref \
  --cand "$B" \
  --cand "$B;args=--pcie-frac 0.3" \
  --cand "$B;args=--pcie-frac 0.4" \
  --cand "$B;STRATA_HC_PERSIST=1" \
  --cand "$B;STRATA_HC_Q8=1" \
  --cand "$NF;STRATA_ADAPT_FETCH=2" \
  --cand "$B;STRATA_HC_PERSIST=1" \
  --cand "$B;args=--pcie-frac 0.4" \
  --cand "$B;args=--pcie-frac 0.3" \
  --cand "$NF;STRATA_ADAPT_FETCH=2" \
  --cand "$B;STRATA_HC_Q8=1" \
  --cand "$B"
echo "exit=$?"
echo idle > runs/TAG
