#!/bin/bash
# Interleaved rounds of pool_replay_bench arms (this machine is shared, so single runs drift): every round runs every arm once,
# in order, then the medians.  An arm is "name|ENV=1 ENV2=2|bench args".
#   bash replay_rounds.sh NAME ROUNDS DUMP "base||" "dag2|STRATA_POOL_DAG=2|" "t96||--tasks 96"
# Output: runs/cpu/NAME/<arm>-r<round>.txt and runs.txt (arm, ms of pool calls a window, output hash).
LAB=$(cd "$(dirname "$0")" && pwd)
ROOT=${STRATA_DIR:-$(cd "$LAB/../.." && pwd)}
B=$ROOT/build-sm86/pool_replay_bench.exe
NAME=$1; ROUNDS=$2; DUMP=$3; shift 3
O=$LAB/runs/cpu/$NAME
mkdir -p "$O"
for r in $(seq 1 "$ROUNDS"); do
  for arm in "$@"; do
    IFS='|' read -r name envs args <<< "$arm"
    f=$O/$name-r$r.txt
    env X=1 $envs "$B" "$DUMP" --pack "$ROOT/packs/iq3_xxs" --windows 600 --skip 200 --reps 1 $args > "$f" 2>&1
    ms=$(grep -oE "per window: [0-9.]+" "$f" | grep -oE "[0-9.]+$")
    h=$(grep -oE "hash [0-9a-f]+" "$f")
    echo "r$r $name $ms $h"
  done
done | tee "$O/runs.txt"
echo "== medians (ms of pool calls per window)"
awk '{a[$2]=a[$2]" "$3} END {for (k in a) print k, a[k]}' "$O/runs.txt" | while read -r name vals; do
  med=$(echo $vals | tr ' ' '\n' | sort -n | awk '{v[NR]=$1} END {print (NR%2? v[(NR+1)/2] : (v[NR/2]+v[NR/2+1])/2)}')
  echo "$name median $med  [$vals]"
done
