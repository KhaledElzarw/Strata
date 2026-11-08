#!/usr/bin/env bash
# Quality guard, 65 prompts x 400 forced tokens:
#  1. DFlash2 (decode-path change): its continuations (set2C) scored by the stock engine, against stock2A / stock2B.
#  2. DFlash2 + --expert-cache 7000 (scorer change: more experts on the GPU, other rounding): the stock continuations
#     (set2A) scored by the candidate engine, against two stock scorings of the same set (stock2A, stock2A-rep).
set -u
cd /d/Projects/local_ai/strata-lab/runs/fc || exit 1
FC="python /c/src/Strata/tools/force_check.py"
[ -f cand2-df2c65.tsv.meta.json ] || $FC score cfg-stock.json set2C-df2c65.json cand2-df2c65.tsv || exit 1
$FC check --stock stock2A.tsv stock2B.tsv --cand cand2-df2c65.tsv --json check2-df2c65.json
echo "DF2 check exit $? (0 pass, 1 reject, 2 inconclusive)"
[ -f stock2A-rep.tsv.meta.json ] || $FC score cfg-stock.json set2A.json stock2A-rep.tsv || exit 1
[ -f cand2-df2ec7000.tsv.meta.json ] || $FC score cfg-df2ec7000.json set2A.json cand2-df2ec7000.tsv || exit 1
$FC check --stock stock2A.tsv stock2A-rep.tsv --cand cand2-df2ec7000.tsv --json check2-df2ec7000.json
echo "DF2+ec7000 check exit $? (0 pass, 1 reject, 2 inconclusive)"
