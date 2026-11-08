#!/usr/bin/env bash
# Quality guard for DFlash2, round 2: 65 prompts x 400 forced tokens (round 1, 20 x 300, was INCONCLUSIVE: +0.28 pts,
# CI90 -0.52..+1.10). Continuations from stock (twice) and from DFlash2, all scored by the stock engine.
set -u
cd /d/Projects/local_ai/strata-lab/runs/fc || exit 1
FC="python /c/src/Strata/tools/force_check.py"
G="--corpus corpus2.jsonl --per-kind 13 --offset 0 --new 400"
[ -f set2A.json ] || $FC gen cfg-stock.json set2A.json $G || exit 1
[ -f set2B.json ] || $FC gen cfg-stock.json set2B.json $G || exit 1
[ -f set2C-df2c65.json ] || $FC gen cfg-df2c65.json set2C-df2c65.json $G || exit 1
[ -f stock2A.tsv ] || $FC score cfg-stock.json set2A.json stock2A.tsv || exit 1
[ -f stock2B.tsv ] || $FC score cfg-stock.json set2B.json stock2B.tsv || exit 1
[ -f cand2-df2c65.tsv ] || $FC score cfg-stock.json set2C-df2c65.json cand2-df2c65.tsv || exit 1
$FC check --stock stock2A.tsv stock2B.tsv --cand cand2-df2c65.tsv --json check2-df2c65.json
echo "check exit $? (0 pass, 1 reject, 2 inconclusive)"
