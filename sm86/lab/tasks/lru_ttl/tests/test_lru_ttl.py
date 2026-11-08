import pytest

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
