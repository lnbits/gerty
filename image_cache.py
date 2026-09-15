"""Bounded process-local snapshot cache; restart/eviction requires a new manifest."""

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from time import monotonic

MAX_BYTES = 32 * 1024 * 1024
MAX_AGE = 24 * 60 * 60


@dataclass
class Snapshot:
    key: str
    png: bytes
    created: float
    fresh_until: float
    revision: str


class ImageCache:
    def __init__(self, max_bytes=MAX_BYTES, max_age=MAX_AGE):
        self.entries = OrderedDict()
        self.max_bytes = max_bytes
        self.max_age = max_age
        self.size = 0
        self.lock = asyncio.Lock()

    def prune(self):
        now = monotonic()
        for revision, snapshot in list(self.entries.items()):
            if now - snapshot.created >= self.max_age:
                self.size -= len(snapshot.png)
                del self.entries[revision]

    def get(self, revision):
        self.prune()
        return self.entries.get(revision)

    def fresh(self, key):
        self.prune()
        now = monotonic()
        return next(
            (
                s
                for s in reversed(self.entries.values())
                if s.key == key and s.fresh_until > now
            ),
            None,
        )

    def put(self, key, png, refresh):
        self.prune()
        revision = sha256(key.encode() + png).hexdigest()
        now = monotonic()
        previous = self.entries.pop(revision, None)
        if previous:
            self.size -= len(previous.png)
        snapshot = Snapshot(key, png, now, now + refresh, revision)
        if len(png) > self.max_bytes:
            raise ValueError("Image exceeds cache capacity")
        self.entries[revision] = snapshot
        self.size += len(png)
        while self.size > self.max_bytes:
            _, removed = self.entries.popitem(last=False)
            self.size -= len(removed.png)
        return snapshot


image_cache = ImageCache()
