#!/bin/bash
# After the council L2 fixes (build res14, commit adc1c1294): q3 + RES and q3 vs the reference.
# stack (q3: the 5 tier-A switches of sweep18).
cd /d/Projects/local_ai/strata-lab || exit 2
echo sweep21 > runs/TAG
mkdir -p runs/id/sweep21 && cp runs/id/sweep1/ref.tsv* runs/id/sweep21/
E='exe=C:\src\Strata\build-sm86\strata.exe'
S="STRATA_FETCH_FORK=1;STRATA_GRAPH_PRIO=1;STRATA_MMVQ_IL_3090=1;STRATA_EXP_MODE=9;STRATA_DECODE_TIMING=1"
N="$E;STRATA_GR_DOWN86=1;STRATA_GR_UP_WIDE=1;STRATA_GR_UP_HYB=3;STRATA_GR_XN=1;$S;STRATA_EXP9_DOWN=42:10"
Q="$N;STRATA_DOORBELL_STORE=1;STRATA_FUSE_HITS=1;STRATA_ACTQ_SKIP=1;STRATA_GR_UP_PL=1;STRATA_GR_D87=8"
python idcheck.py sweep21 --reuse-ref --cand "$Q;STRATA_GR_RES=1" --cand "$Q"
echo "exit=$?"
echo idle > runs/TAG
