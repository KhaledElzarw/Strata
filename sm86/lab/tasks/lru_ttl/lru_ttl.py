import time


class LRUCache:
    def __init__(self, capacity, ttl=None, clock=time.monotonic):
        raise NotImplementedError

    def get(self, key, default=None):
        raise NotImplementedError

    def put(self, key, value):
        raise NotImplementedError
