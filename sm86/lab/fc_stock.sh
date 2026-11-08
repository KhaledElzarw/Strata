#!/usr/bin/env bash
# Quality-guard reference: greedy continuations of the 20 corpus prompts with the stock engine, then two stock scorings
# (the noise arms every candidate is checked against). Run with no other engine on the GPU.
set -u
LAB=/d/Projects/local_ai/strata-lab
FC="python /c/src/Strata/tools/force_check.py"
cd "$LAB/runs/fc" || exit 1
$FC gen cfg-stock.json set-stock.json --corpus corpus.jsonl --per-kind 4 --offset 0 --new 300 || exit 1
$FC score cfg-stock.json set-stock.json stock1.tsv || exit 1
$FC score cfg-stock.json set-stock.json stock2.tsv || exit 1
$FC check --stock stock1.tsv stock2.tsv --cand stock2.tsv --json selfcheck.json; echo "selfcheck exit $?"
