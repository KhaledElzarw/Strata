"""Writes the 6 code tasks (tasks/<name>/: TASK.md, the code to change, tests/) and their reference solutions
(tasks_ref/<name>/, never shown to an agent). `python make_tasks.py --check` proves each task is fair: the tests fail
on the starting code and pass with the reference solution."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LAB = Path(__file__).parent
FOOT = ("\n\nRun `python -m pytest -q` in this folder to check your work, and keep going until every test passes. "
        "Do not change anything under `tests/`. Use only the Python standard library.\n")

TASKS = {}

TASKS["lru_ttl"] = {
    "TASK.md": """# LRU cache with expiry

Implement `LRUCache` in `lru_ttl.py`: a least-recently-used cache whose entries also expire.

- `LRUCache(capacity, ttl=None, clock=time.monotonic)`. `capacity < 1` raises `ValueError`. `ttl=None` means entries
  never expire. `clock` is a zero-argument function returning seconds.
- An entry put at time `t` expires at `t + ttl`: it is expired once `clock() >= t + ttl`.
- `get(key, default=None)` returns the value, or `default` when the key is missing or expired. A hit makes the key the
  most recently used. An expired entry is removed. `get` does not extend an entry's expiry.
- `put(key, value)` inserts or replaces the entry, restarts its expiry and makes it the most recently used. Expired
  entries are dropped first; then least recently used entries are evicted until at most `capacity` remain.
- `len(cache)` is the number of live (unexpired) entries. `key in cache` is True only for a live entry and does not
  change recency.""",
    "lru_ttl.py": '''import time


class LRUCache:
    def __init__(self, capacity, ttl=None, clock=time.monotonic):
        raise NotImplementedError

    def get(self, key, default=None):
        raise NotImplementedError

    def put(self, key, value):
        raise NotImplementedError
''',
    "tests/test_lru_ttl.py": '''import pytest

from lru_ttl import LRUCache


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_basic_get_put():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert c.get("a") == 1 and c.get("b") == 2
    assert c.get("x") is None and c.get("x", 7) == 7


def test_evicts_least_recently_used():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.get("a")
    c.put("c", 3)
    assert "b" not in c and c.get("a") == 1 and c.get("c") == 3


def test_put_existing_refreshes_recency_and_value():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    c.put("a", 10)
    c.put("c", 3)
    assert c.get("a") == 10 and "b" not in c


def test_capacity_validation():
    with pytest.raises(ValueError):
        LRUCache(0)


def test_ttl_expiry():
    clk = Clock()
    c = LRUCache(3, ttl=10, clock=clk)
    c.put("a", 1)
    clk.t = 9.9
    assert c.get("a") == 1
    clk.t = 10.0
    assert c.get("a") is None and len(c) == 0


def test_put_resets_ttl():
    clk = Clock()
    c = LRUCache(3, ttl=10, clock=clk)
    c.put("a", 1)
    clk.t = 8
    c.put("a", 2)
    clk.t = 15
    assert c.get("a") == 2


def test_get_does_not_reset_ttl():
    clk = Clock()
    c = LRUCache(3, ttl=10, clock=clk)
    c.put("a", 1)
    clk.t = 8
    c.get("a")
    clk.t = 10
    assert c.get("a") is None


def test_len_counts_live_only():
    clk = Clock()
    c = LRUCache(5, ttl=5, clock=clk)
    c.put("a", 1)
    clk.t = 3
    c.put("b", 2)
    clk.t = 6
    assert len(c) == 1 and "a" not in c and "b" in c


def test_expired_dropped_before_evicting_live():
    clk = Clock()
    c = LRUCache(2, ttl=5, clock=clk)
    c.put("old", 1)
    clk.t = 4
    c.put("live", 2)
    clk.t = 6
    c.put("new", 3)
    assert "live" in c and "new" in c and len(c) == 2


def test_contains_does_not_touch_recency():
    c = LRUCache(2)
    c.put("a", 1)
    c.put("b", 2)
    assert "a" in c
    c.put("c", 3)
    assert "a" not in c and "b" in c


def test_no_ttl_never_expires():
    clk = Clock()
    c = LRUCache(1, clock=clk)
    c.put("a", 1)
    clk.t = 1e9
    assert c.get("a") == 1
''',
    "ref/lru_ttl.py": '''import time
from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity, ttl=None, clock=time.monotonic):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self._d = OrderedDict()

    def _expired(self, exp):
        return exp is not None and self.clock() >= exp

    def _purge(self):
        for k in [k for k, (_, e) in self._d.items() if self._expired(e)]:
            del self._d[k]

    def get(self, key, default=None):
        item = self._d.get(key)
        if item is None:
            return default
        if self._expired(item[1]):
            del self._d[key]
            return default
        self._d.move_to_end(key)
        return item[0]

    def put(self, key, value):
        self._d[key] = (value, None if self.ttl is None else self.clock() + self.ttl)
        self._d.move_to_end(key)
        self._purge()
        while len(self._d) > self.capacity:
            self._d.popitem(last=False)

    def __len__(self):
        self._purge()
        return len(self._d)

    def __contains__(self, key):
        item = self._d.get(key)
        return item is not None and not self._expired(item[1])
''',
}

TASKS["csv_line"] = {
    "TASK.md": """# Fix the CSV line parser

`parse_line` in `csvline.py` has bugs. Fix them so it follows its docstring and the tests pass.""",
    "csvline.py": '''def parse_line(line, sep=","):
    """Split one CSV line into fields.

    Fields are separated by `sep`. A field may be wrapped in double quotes; inside quotes `sep` is an ordinary
    character and two double quotes ("") stand for one. Whitespace is kept exactly as written. An empty line is one
    empty field. A quote that is never closed raises ValueError.
    """
    fields = []
    cur = ""
    quoted = False
    for ch in line:
        if quoted:
            if ch == '"':
                quoted = False
            else:
                cur += ch
        elif ch == '"':
            quoted = True
        elif ch == sep:
            fields.append(cur.strip())
            cur = ""
        else:
            cur += ch
    fields.append(cur.strip())
    return fields
''',
    "tests/test_csvline.py": '''import pytest

from csvline import parse_line


def test_simple():
    assert parse_line("a,b,c") == ["a", "b", "c"]


def test_empty_fields():
    assert parse_line("a,,b") == ["a", "", "b"]


def test_trailing_sep():
    assert parse_line("a,b,") == ["a", "b", ""]


def test_empty_line():
    assert parse_line("") == [""]


def test_quoted_sep():
    assert parse_line('"a,b",c') == ["a,b", "c"]


def test_escaped_quote():
    assert parse_line('"say ""hi""",x') == ['say "hi"', "x"]


def test_whitespace_kept():
    assert parse_line(" a , b ") == [" a ", " b "]


def test_quoted_whitespace():
    assert parse_line('"  x  ",y') == ["  x  ", "y"]


def test_unterminated_quote():
    with pytest.raises(ValueError):
        parse_line('"abc,d')


def test_custom_sep():
    assert parse_line('a;"b;c";d', sep=";") == ["a", "b;c", "d"]


def test_only_quotes():
    assert parse_line('""') == [""]


def test_quoted_empty_between():
    assert parse_line('a,"",b') == ["a", "", "b"]
''',
    "ref/csvline.py": '''def parse_line(line, sep=","):
    fields, cur, quoted, i = [], [], False, 0
    while i < len(line):
        ch = line[i]
        if quoted:
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    cur.append('"')
                    i += 1
                else:
                    quoted = False
            else:
                cur.append(ch)
        elif ch == '"':
            quoted = True
        elif ch == sep:
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    if quoted:
        raise ValueError("unterminated quote")
    fields.append("".join(cur))
    return fields
''',
}

TASKS["intervals"] = {
    "TASK.md": """# Interval helpers

Implement the four functions in `intervals.py` as their docstrings describe. Intervals are half-open `[start, end)`.""",
    "intervals.py": '''def merge(intervals):
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
''',
    "tests/test_intervals.py": '''import pytest

from intervals import covered, gaps, insert, merge


def test_merge_overlapping():
    assert merge([(1, 4), (2, 6), (8, 10)]) == [(1, 6), (8, 10)]


def test_merge_touching():
    assert merge([(1, 3), (3, 5)]) == [(1, 5)]


def test_merge_unsorted():
    assert merge([(5, 7), (1, 2), (2, 3)]) == [(1, 3), (5, 7)]


def test_merge_contained():
    assert merge([(1, 10), (2, 3), (4, 5)]) == [(1, 10)]


def test_merge_drops_empty():
    assert merge([(1, 1), (2, 3), (4, 4)]) == [(2, 3)]


def test_merge_empty_input():
    assert merge([]) == []


def test_merge_returns_tuples():
    assert merge([[1, 2]]) == [(1, 2)]


def test_merge_invalid():
    with pytest.raises(ValueError):
        merge([(3, 1)])


def test_merge_does_not_mutate():
    src = [(2, 3), (1, 2)]
    merge(src)
    assert src == [(2, 3), (1, 2)]


def test_insert():
    assert insert([(1, 2), (5, 6)], (2, 5)) == [(1, 6)]


def test_insert_separate():
    assert insert([(1, 2)], (4, 5)) == [(1, 2), (4, 5)]


def test_covered():
    assert covered([(1, 4), (2, 6), (10, 11)]) == 6


def test_covered_floats():
    assert covered([(0.5, 1.5), (1.0, 2.0)]) == pytest.approx(1.5)


def test_gaps():
    assert gaps([(2, 3), (5, 7)], 0, 10) == [(0, 2), (3, 5), (7, 10)]


def test_gaps_clipped():
    assert gaps([(-5, 2), (8, 20)], 0, 10) == [(2, 8)]


def test_gaps_none():
    assert gaps([(0, 10)], 0, 10) == []
''',
    "ref/intervals.py": '''def merge(intervals):
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
''',
}

TASKS["wordfreq"] = {
    "TASK.md": """# Word frequency command-line tool

Write `wordfreq.py`, run as `python wordfreq.py FILE [-n N] [--min-len K]`.

- It reads FILE as UTF-8. A word is a run of letters (any Unicode letter) and apostrophes, compared in lower case.
  Apostrophes at the start or end of a word are removed; a word left empty is ignored. Digits and underscores are not
  part of words.
- It prints the N most frequent words (default 10), one per line as `word count` with a single space, most frequent
  first; ties are broken alphabetically.
- `--min-len K` ignores words shorter than K characters (after the outer apostrophes are removed). The default is 1.
- A file that cannot be read prints `error: cannot read FILE` to stderr and exits with status 1.
- N must be a positive integer; anything else is an argparse usage error (exit status 2).""",
    "wordfreq.py": "",
    "tests/test_wordfreq.py": '''import os
import subprocess
import sys
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / "wordfreq.py"


def run(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", env=env)


def write(tmp_path, text):
    p = tmp_path / "in.txt"
    p.write_text(text, encoding="utf-8")
    return p


def test_counts_and_order(tmp_path):
    r = run(write(tmp_path, "the cat and the hat. The end!"))
    assert r.returncode == 0
    assert r.stdout.splitlines() == ["the 3", "and 1", "cat 1", "end 1", "hat 1"]


def test_top_n(tmp_path):
    assert run(write(tmp_path, "b b b a a c"), "-n", 2).stdout.splitlines() == ["b 3", "a 2"]


def test_apostrophes(tmp_path):
    out = run(write(tmp_path, "Don't 'quote' don't rock'n'roll ''")).stdout.splitlines()
    assert out == ["don't 2", "quote 1", "rock'n'roll 1"]


def test_unicode_letters(tmp_path):
    out = run(write(tmp_path, "Caf\\u00e9 caf\\u00e9 na\\u00efve 123 4x")).stdout.splitlines()
    assert out == ["caf\\u00e9 2", "na\\u00efve 1", "x 1"]


def test_min_len(tmp_path):
    assert run(write(tmp_path, "a an ant ants a an"), "--min-len", 3).stdout.splitlines() == ["ant 1", "ants 1"]


def test_missing_file(tmp_path):
    r = run(tmp_path / "nope.txt")
    assert r.returncode == 1 and "error: cannot read" in r.stderr


def test_bad_n(tmp_path):
    assert run(write(tmp_path, "x"), "-n", 0).returncode == 2
''',
    "ref/wordfreq.py": '''import argparse
import re
import sys
from collections import Counter

WORD = re.compile(r"(?:[^\\W\\d_]|')+")


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
''',
}

TASKS["bank"] = {
    "TASK.md": """# Refactor the bank module

Refactor `bank.py`:

1. Add a class `Bank` that holds its own accounts, with methods `open_account(name, initial=0)`, `deposit(name,
   amount)`, `withdraw(name, amount)`, `balance(name)` and `transfer(src, dst, amount)`. Two `Bank` instances never
   share accounts.
2. Amounts are integers (cents). `deposit`, `withdraw` and `transfer` need `amount > 0`, else `ValueError`. `initial`
   must be `>= 0`, else `ValueError`. An unknown account raises `KeyError`. Opening an existing account raises
   `ValueError`. `transfer` to the same account raises `ValueError`.
3. Add `class InsufficientFunds(ValueError)`. `withdraw` and `transfer` raise it when the source balance is smaller
   than `amount`. A call that raises leaves every balance unchanged.
4. Keep the module-level functions `open_account`, `deposit`, `withdraw` and `balance` working for existing callers,
   now delegating to a module-level `Bank` instance named `default_bank`, and add a module-level `transfer` the same
   way.""",
    "bank.py": '''"""Account helpers. Balances are integer cents."""
_accounts = {}


def open_account(name, initial=0):
    if name in _accounts:
        raise ValueError("account exists: " + name)
    _accounts[name] = initial


def deposit(name, amount):
    _accounts[name] += amount


def withdraw(name, amount):
    _accounts[name] -= amount


def balance(name):
    return _accounts[name]
''',
    "tests/test_bank.py": '''import pytest

import bank
from bank import Bank, InsufficientFunds


def test_basic_flow():
    b = Bank()
    b.open_account("a", 100)
    b.deposit("a", 50)
    b.withdraw("a", 30)
    assert b.balance("a") == 120


def test_transfer():
    b = Bank()
    b.open_account("a", 100)
    b.open_account("b")
    b.transfer("a", "b", 40)
    assert (b.balance("a"), b.balance("b")) == (60, 40)


def test_insufficient_funds_leaves_balances():
    b = Bank()
    b.open_account("a", 10)
    b.open_account("b", 5)
    with pytest.raises(InsufficientFunds):
        b.transfer("a", "b", 11)
    with pytest.raises(InsufficientFunds):
        b.withdraw("b", 6)
    assert (b.balance("a"), b.balance("b")) == (10, 5)


def test_insufficient_is_value_error():
    assert issubclass(InsufficientFunds, ValueError)


@pytest.mark.parametrize("amount", [0, -5])
def test_non_positive_amounts(amount):
    b = Bank()
    b.open_account("a", 10)
    b.open_account("b")
    for call in (lambda: b.deposit("a", amount), lambda: b.withdraw("a", amount),
                 lambda: b.transfer("a", "b", amount)):
        with pytest.raises(ValueError):
            call()
    assert b.balance("a") == 10


def test_unknown_accounts():
    b = Bank()
    b.open_account("a", 10)
    with pytest.raises(KeyError):
        b.balance("zz")
    with pytest.raises(KeyError):
        b.deposit("zz", 1)
    with pytest.raises(KeyError):
        b.transfer("a", "zz", 1)
    assert b.balance("a") == 10


def test_duplicate_and_negative_initial():
    b = Bank()
    b.open_account("a")
    with pytest.raises(ValueError):
        b.open_account("a")
    with pytest.raises(ValueError):
        b.open_account("n", -1)


def test_self_transfer():
    b = Bank()
    b.open_account("a", 10)
    with pytest.raises(ValueError):
        b.transfer("a", "a", 1)


def test_instances_are_independent():
    b1, b2 = Bank(), Bank()
    b1.open_account("a", 1)
    with pytest.raises(KeyError):
        b2.balance("a")


def test_legacy_functions_use_default_bank():
    bank.open_account("legacy-x", 5)
    bank.deposit("legacy-x", 5)
    bank.withdraw("legacy-x", 3)
    assert bank.balance("legacy-x") == 7 and bank.default_bank.balance("legacy-x") == 7
    bank.open_account("legacy-y")
    bank.transfer("legacy-x", "legacy-y", 7)
    assert bank.balance("legacy-y") == 7
    with pytest.raises(InsufficientFunds):
        bank.withdraw("legacy-x", 1)
''',
    "ref/bank.py": '''class InsufficientFunds(ValueError):
    pass


class Bank:
    def __init__(self):
        self._accounts = {}

    def _need(self, name):
        if name not in self._accounts:
            raise KeyError(name)

    @staticmethod
    def _positive(amount):
        if amount <= 0:
            raise ValueError("amount must be positive")

    def open_account(self, name, initial=0):
        if name in self._accounts:
            raise ValueError("account exists: " + name)
        if initial < 0:
            raise ValueError("initial balance must be >= 0")
        self._accounts[name] = initial

    def deposit(self, name, amount):
        self._need(name)
        self._positive(amount)
        self._accounts[name] += amount

    def withdraw(self, name, amount):
        self._need(name)
        self._positive(amount)
        if self._accounts[name] < amount:
            raise InsufficientFunds(name)
        self._accounts[name] -= amount

    def balance(self, name):
        self._need(name)
        return self._accounts[name]

    def transfer(self, src, dst, amount):
        self._need(src)
        self._need(dst)
        self._positive(amount)
        if src == dst:
            raise ValueError("same account")
        if self._accounts[src] < amount:
            raise InsufficientFunds(src)
        self._accounts[src] -= amount
        self._accounts[dst] += amount


default_bank = Bank()


def open_account(name, initial=0):
    default_bank.open_account(name, initial)


def deposit(name, amount):
    default_bank.deposit(name, amount)


def withdraw(name, amount):
    default_bank.withdraw(name, amount)


def balance(name):
    return default_bank.balance(name)


def transfer(src, dst, amount):
    default_bank.transfer(src, dst, amount)
''',
}

TASKS["jsondiff"] = {
    "TASK.md": """# Structural JSON diff

Implement `diff(a, b)` in `jsondiff.py`. `a` and `b` are JSON-like values (dict, list, str, int, float, bool, None).
It returns a sorted list of strings describing how to get from `a` to `b`:

- `+ PATH: VALUE` for something only in `b`, `- PATH: VALUE` for something only in `a`, and `~ PATH: OLD -> NEW` for a
  changed value.
- Dicts are compared key by key and lists index by index; extra list items at the end are `+` or `-` entries. The
  diff goes inside a dict or list only when both sides at that path are the same kind of container. Any other
  difference is a `~`, and two values are equal only when they have the same type and compare equal (so `1`, `1.0`,
  `True` and `"1"` all differ from each other).
- PATH starts with `$`; a dict key adds `.key` and a list index adds `[i]`. Values are written with
  `json.dumps(value, sort_keys=True)`.
- Equal inputs give `[]`.""",
    "jsondiff.py": '''def diff(a, b):
    raise NotImplementedError
''',
    "tests/test_jsondiff.py": '''from jsondiff import diff


def test_equal():
    assert diff({"a": [1, {"b": None}]}, {"a": [1, {"b": None}]}) == []


def test_scalar_change():
    assert diff(1, 2) == ["~ $: 1 -> 2"]


def test_dict_add_remove_change():
    assert diff({"a": 1, "b": 2}, {"b": 3, "c": 4}) == ["+ $.c: 4", "- $.a: 1", "~ $.b: 2 -> 3"]


def test_nested():
    assert diff({"x": {"y": {"z": 1}}}, {"x": {"y": {"z": 2}}}) == ["~ $.x.y.z: 1 -> 2"]


def test_lists():
    assert diff([1, 2, 3], [1, 5]) == ["- $[2]: 3", "~ $[1]: 2 -> 5"]
    assert diff([1], [1, [2]]) == ["+ $[1]: [2]"]


def test_type_change():
    assert diff({"a": 1}, {"a": "1"}) == ['~ $.a: 1 -> "1"']
    assert diff({"a": 1}, {"a": True}) == ["~ $.a: 1 -> true"]
    assert diff({"a": 1}, {"a": 1.0}) == ["~ $.a: 1 -> 1.0"]
    assert diff({"a": [1]}, {"a": {"0": 1}}) == ['~ $.a: [1] -> {"0": 1}']


def test_values_rendered_with_sorted_keys():
    assert diff({}, {"k": {"b": 1, "a": 2}}) == ['+ $.k: {"a": 2, "b": 1}']


def test_list_of_dicts():
    assert diff([{"id": 1, "v": "a"}], [{"id": 1, "v": "b"}]) == ['~ $[0].v: "a" -> "b"']
''',
    "ref/jsondiff.py": '''import json


def _same(x, y):
    return type(x) is type(y) and x == y


def diff(a, b):
    out = []

    def dump(v):
        return json.dumps(v, sort_keys=True)

    def walk(p, x, y):
        if isinstance(x, dict) and isinstance(y, dict):
            for k in x.keys() | y.keys():
                q = "%s.%s" % (p, k)
                if k not in y:
                    out.append("- %s: %s" % (q, dump(x[k])))
                elif k not in x:
                    out.append("+ %s: %s" % (q, dump(y[k])))
                else:
                    walk(q, x[k], y[k])
        elif isinstance(x, list) and isinstance(y, list):
            for i in range(max(len(x), len(y))):
                q = "%s[%d]" % (p, i)
                if i >= len(y):
                    out.append("- %s: %s" % (q, dump(x[i])))
                elif i >= len(x):
                    out.append("+ %s: %s" % (q, dump(y[i])))
                else:
                    walk(q, x[i], y[i])
        elif not _same(x, y):
            out.append("~ %s: %s -> %s" % (p, dump(x), dump(y)))

    walk("$", a, b)
    return sorted(out)
''',
}


def write_all():
    for name, files in TASKS.items():
        task, ref = LAB / "tasks" / name, LAB / "tasks_ref" / name
        for d in (task, ref):
            if d.exists():
                shutil.rmtree(d)
        for rel, text in files.items():
            if rel.startswith("ref/"):
                dst = ref / rel[4:]
            else:
                dst = task / rel
                if rel == "TASK.md":
                    text = text + FOOT
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text, encoding="utf-8")
    print("wrote", ", ".join(TASKS))


def pytest_in(folder: Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=folder,
                       capture_output=True, text=True)
    return r.returncode, (r.stdout.strip().splitlines() or [""])[-1]


def check():
    ok = True
    for name in TASKS:
        with tempfile.TemporaryDirectory() as t:
            start = Path(t) / "start"
            shutil.copytree(LAB / "tasks" / name, start)
            rc0, line0 = pytest_in(start)
            solved = Path(t) / "solved"
            shutil.copytree(LAB / "tasks" / name, solved)
            for f in (LAB / "tasks_ref" / name).iterdir():
                shutil.copy(f, solved / f.name)
            rc1, line1 = pytest_in(solved)
        fair = rc0 != 0 and rc1 == 0
        ok &= fair
        print(f"{name:10s} start: {line0!r:45s} reference: {line1!r:30s} {'OK' if fair else 'BROKEN'}")
    return ok


if __name__ == "__main__":
    write_all()
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
