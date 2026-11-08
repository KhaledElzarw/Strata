#!/usr/bin/env bash
# Quality guard round 4, part 3: the cross check.  Part 2 scored stock (MTP) text and DFlash2 text with the stock
# scorer, whose verify windows are MTP-shaped; here the same four sets are scored by the DFlash2 engine (cfg-c65, same
# pinned cache).  If the DFlash2 scorer favors DFlash2 text by about what the stock scorer favors stock text, the +0.2
# points of part 2 are the arithmetic path, not the text.
set -u
cd /d/Projects/local_ai/strata-lab/runs/fc || exit 1
FC="python /c/src/Strata/tools/force_check.py"
for s in set3A set3B set3C-c65 set3D-c65; do
  [ -f x3-$s.tsv.meta.json ] || $FC score cfg-c65.json $s.json x3-$s.tsv || exit 1
done
echo "--- DFlash2 scorer: stock text (cand) against DFlash2 text (reference)"
python ../../pooled_check.py --stock x3-set3C-c65.tsv x3-set3D-c65.tsv --cand x3-set3A.tsv x3-set3B.tsv --json check3x-stock-under-df2.json
echo "--- stock scorer: DFlash2 text (cand) against stock text (reference)"
python ../../pooled_check.py --stock s3-set3A.tsv s3-set3B.tsv --cand s3-set3C-c65.tsv s3-set3D-c65.tsv --json check3-c65-pooled.json
