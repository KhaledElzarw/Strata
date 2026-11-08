def merge(intervals):
    """Merge half-open intervals [start, end).

    Returns a new sorted list of (start, end) tuples in which overlapping or touching intervals ([1, 3) and [3, 5))
    are joined. Empty intervals (start == end) are dropped. An interval with start > end raises ValueError. The input
    (any iterable of pairs) is not modified.
    """
    raise NotImplementedError


def insert(intervals, new):
    """Add `new` to `intervals` and return the merged result."""
    raise NotImplementedError


def covered(intervals):
    """Total length covered by the intervals, overlaps counted once."""
    raise NotImplementedError


def gaps(intervals, lo, hi):
    """The parts of [lo, hi) no interval covers, as a sorted list of (start, end) tuples."""
    raise NotImplementedError
