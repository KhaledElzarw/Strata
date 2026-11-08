# LRU cache with expiry

Implement `LRUCache` in `lru_ttl.py`: a least-recently-used cache whose entries also expire.

- `LRUCache(capacity, ttl=None, clock=time.monotonic)`. `capacity < 1` raises `ValueError`. `ttl=None` means entries
  never expire. `clock` is a zero-argument function returning seconds.
- An entry put at time `t` expires at `t + ttl`: it is expired once `clock() >= t + ttl`.
- `get(key, default=None)` returns the value, or `default` when the key is missing or expired. A hit makes the key the
  most recently used. An expired entry is removed. `get` does not extend an entry's expiry.
- `put(key, value)` inserts or replaces the entry, restarts its expiry and makes it the most recently used. Expired
  entries are dropped first; then least recently used entries are evicted until at most `capacity` remain.
- `len(cache)` is the number of live (unexpired) entries. `key in cache` is True only for a live entry and does not
  change recency.

Run `python -m pytest -q` in this folder to check your work, and keep going until every test passes. Do not change anything under `tests/`. Use only the Python standard library.
