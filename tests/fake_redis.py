"""Thread-safe in-memory Redis mock for offline unit and FastAPI TestClient suites."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Any


class FakePubSub:
    def __init__(self, broker: dict[str, list[deque[str]]]) -> None:
        self._broker = broker
        self._channels: list[str] = []
        self._queue: deque[dict[str, Any]] = deque()

    def subscribe(self, channel: str) -> None:
        self._channels.append(channel)
        self._broker[channel].append(self._queue)

    def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 0.0):
        if self._queue:
            return self._queue.popleft()
        return None

    def unsubscribe(self) -> None:
        for ch in self._channels:
            if self._queue in self._broker.get(ch, []):
                self._broker[ch].remove(self._queue)
        self._channels.clear()

    def close(self) -> None:
        self.unsubscribe()


class FakeRedis:
    def __init__(self) -> None:
        self._kv: dict[str, tuple[str, float | None]] = {}
        self._lists: dict[str, deque[str]] = defaultdict(deque)
        self._pubsub: dict[str, list[deque[Any]]] = defaultdict(list)

    def _evict_if_expired(self, key: str) -> None:
        entry = self._kv.get(key)
        if entry is None:
            return
        _, expires_at = entry
        if expires_at is not None and time.time() >= expires_at:
            del self._kv[key]

    def ping(self) -> bool:
        return True

    def get(self, key: str) -> str | None:
        self._evict_if_expired(key)
        entry = self._kv.get(key)
        return entry[0] if entry else None

    def setex(self, key: str, seconds: int, value: str) -> bool:
        self._kv[key] = (value, time.time() + seconds)
        return True

    def ttl(self, key: str) -> int:
        self._evict_if_expired(key)
        entry = self._kv.get(key)
        if not entry:
            return -2
        if entry[1] is None:
            return -1
        return max(1, int(entry[1] - time.time()))

    def exists(self, key: str) -> int:
        self._evict_if_expired(key)
        return 1 if key in self._kv else 0

    def delete(self, *keys: str) -> int:
        removed = 0
        for k in keys:
            if k in self._kv:
                del self._kv[k]
                removed += 1
        return removed

    def lpush(self, queue_name: str, value: str) -> int:
        self._lists[queue_name].appendleft(value)
        return len(self._lists[queue_name])

    def brpop(self, queue_name: str, timeout: int = 1) -> tuple[str, str] | None:
        if self._lists[queue_name]:
            return queue_name, self._lists[queue_name].pop()
        return None

    def publish(self, channel: str, message: str) -> int:
        subscribers = self._pubsub.get(channel, [])
        for q in subscribers:
            q.append({"type": "message", "channel": channel, "data": message})
        return len(subscribers)

    def pubsub(self) -> FakePubSub:
        return FakePubSub(self._pubsub)
