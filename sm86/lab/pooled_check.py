"""force_check's rate rule with SEVERAL candidate arms: the candidate's mismatch rate is the mean of its arms, as the
stock side's is the mean of the stock arms, bootstrapped over the same requests (4000 resamples, 90% two-sided = the
rule's one-sided 95% bounds).  Same thresholds: PASS if the upper bound <= 0.5 points, REJECT if the lower bound > 0.5.

    python pooled_check.py --stock A.tsv B.tsv --cand C.tsv D.tsv [--json out.json]
"""
import argparse
import json
import random
import sys

sys.path.insert(0, r"C:\src\Strata\tools")
import force_check as fc  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", nargs="+", required=True)
    ap.add_argument("--cand", nargs="+", required=True)
    ap.add_argument("--json")
    a = ap.parse_args()
    stock = [fc.load_arm(t) for t in a.stock]
    cand = [fc.load_arm(t) for t in a.cand]
    ids = [i for i in cand[0] if all(i in s for s in stock + cand)]

    def counts(arm):
        return [(len(arm[i]), sum(1 for r in arm[i] if r[0])) for i in ids]

    sc, cc = [counts(s) for s in stock], [counts(c) for c in cand]

    def rate(cs, pick):
        return 100.0 * sum(cs[j][1] for j in pick) / max(1, sum(cs[j][0] for j in pick))

    allj = list(range(len(ids)))
    r_s = [rate(x, allj) for x in sc]
    r_c = [rate(x, allj) for x in cc]
    diff = sum(r_c) / len(r_c) - sum(r_s) / len(r_s)
    rng, diffs = random.Random(1), []
    for _ in range(4000):
        pick = [rng.randrange(len(ids)) for _ in ids]
        diffs.append(sum(rate(x, pick) for x in cc) / len(cc) - sum(rate(x, pick) for x in sc) / len(sc))
    diffs.sort()
    lo, hi = diffs[200], diffs[3799]
    verdict = "REJECT" if lo > 0.5 else ("PASS" if hi <= 0.5 else "INCONCLUSIVE")
    out = {"requests": len(ids), "stock_rates_pct": [round(x, 3) for x in r_s], "cand_rates_pct": [round(x, 3) for x in r_c],
           "diff_pts": round(diff, 3), "diff_ci90_pts": [round(lo, 3), round(hi, 3)], "rate_rule": verdict}
    print(json.dumps(out, indent=1))
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
    sys.exit({"PASS": 0, "REJECT": 1, "INCONCLUSIVE": 2}[verdict])


if __name__ == "__main__":
    main()
