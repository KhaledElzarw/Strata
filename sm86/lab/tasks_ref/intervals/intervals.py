def merge(intervals):
    items = []
    for s, e in intervals:
        if s > e:
            raise ValueError("start > end: %r" % ((s, e),))
        if s < e:
            items.append((s, e))
    items.sort()
    out = []
    for s, e in items:
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def insert(intervals, new):
    return merge(list(intervals) + [tuple(new)])


def covered(intervals):
    return sum(e - s for s, e in merge(intervals))


def gaps(intervals, lo, hi):
    out, cur = [], lo
    for s, e in merge(intervals):
        if e <= lo or s >= hi:
            continue
        s, e = max(s, lo), min(e, hi)
        if s > cur:
            out.append((cur, s))
        cur = max(cur, e)
    if cur < hi:
        out.append((cur, hi))
    return out
