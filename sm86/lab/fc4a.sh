#!/usr/bin/env bash
# Quality guard round 4, part 1: stock (MTP) continuations with the expert cache pinned at 7000 (9,371 slots), so every
# arm of the DFlash2 check runs with the same expert placement (round 2 mixed 6,377- and 9,724-slot runs).
set -u
cd /d/Projects/local_ai/strata-lab/runs/fc || exit 1
FC="python /c/src/Strata/tools/force_check.py"
G="--corpus corpus2.jsonl --per-kind 13 --offset 0 --new 400"
[ -f set3A.json ] || $FC gen cfg-stock-ec7000.json set3A.json $G || exit 1
[ -f set3B.json ] || $FC gen cfg-stock-ec7000.json set3B.json $G || exit 1
echo "part 1 done"
