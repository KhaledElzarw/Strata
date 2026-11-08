import argparse
import re
import sys
from collections import Counter

WORD = re.compile(r"(?:[^\W\d_]|')+")


def positive(s):
    v = int(s)
    if v < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return v


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("-n", type=positive, default=10)
    ap.add_argument("--min-len", type=int, default=1)
    a = ap.parse_args(argv)
    try:
        with open(a.file, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        print("error: cannot read %s" % a.file, file=sys.stderr)
        return 1
    words = (m.group(0).lower().strip("'") for m in WORD.finditer(text))
    c = Counter(w for w in words if w and len(w) >= a.min_len)
    for w, n in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))[: a.n]:
        print("%s %d" % (w, n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
