import time
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
