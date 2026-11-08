#!/usr/bin/env bash
# Quality guard round 4, part 2: the deploy candidate's continuations (DFlash2 + expert cache 7000; CAND = c50 or c65)
# and the pinned-cache stock ones (set3A, set3B from part 1), all scored by the stock engine with the same pinned
# cache (9,371 slots), so every arm has the same expert placement.   ./fc4b.sh c50
set -u
CAND=${1:?usage: fc4b.sh c50|c65}
cd /d/Projects/local_ai/strata-lab/runs/fc || exit 1
FC="python /c/src/Strata/tools/force_check.py"
G="--corpus corpus2.jsonl --per-kind 13 --offset 0 --new 400"
[ -f set3C-$CAND.json ] || $FC gen cfg-$CAND.json set3C-$CAND.json $G || exit 1
[ -f set3D-$CAND.json ] || $FC gen cfg-$CAND.json set3D-$CAND.json $G || exit 1
for s in set3A set3B set3C-$CAND set3D-$CAND; do
  [ -f s3-$s.tsv.meta.json ] || $FC score cfg-stock-ec7000.json $s.json s3-$s.tsv || exit 1
done
$FC check --stock s3-set3A.tsv s3-set3B.tsv --cand s3-set3C-$CAND.tsv --json check3-$CAND-C.json
echo "check C exit $? (0 pass, 1 reject, 2 inconclusive)"
$FC check --stock s3-set3A.tsv s3-set3B.tsv --cand s3-set3D-$CAND.tsv --json check3-$CAND-D.json
echo "check D exit $? (0 pass, 1 reject, 2 inconclusive)"
