"""In-process cost guardrails for a public, anonymous RAG endpoint.

Every uncached query spends a semantic-ranker request (1,000/month free) and
an LLM call. A small TTL cache absorbs repeated demo questions, and a budget
caps how many uncached queries run per minute and per UTC day. State is per
replica; with ``max_replicas = 1`` that is the whole service.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, date, datetime


class AnswerCache[V]:
    """Least-recently-used cache whose entries expire after ``ttl_seconds``."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, V]] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    def get(self, key: str) -> V | None:
        if not self.enabled:
            return None
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= self._clock():
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return value

    def put(self, key: str, value: V) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._entries[key] = (self._clock() + self._ttl, value)
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


class QueryBudget:
    """Token bucket (per minute) plus a hard per-UTC-day ceiling. 0 disables a limit."""

    def __init__(
        self,
        *,
        per_minute: int,
        per_day: int,
        clock: Callable[[], float] = time.monotonic,
        today: Callable[[], date] = lambda: datetime.now(UTC).date(),
    ) -> None:
        self._per_minute = per_minute
        self._per_day = per_day
        self._clock = clock
        self._today = today
        self._tokens = float(per_minute)
        self._refilled_at = clock()
        self._day = today()
        self._used_today = 0
        self._lock = threading.Lock()

    def try_acquire(self) -> float | None:
        """Consume one query; return ``None`` if allowed, else seconds to wait."""

        with self._lock:
            now = self._clock()
            today = self._today()
            if today != self._day:
                self._day, self._used_today = today, 0
            if self._per_day and self._used_today >= self._per_day:
                midnight = datetime.combine(today, datetime.min.time(), tzinfo=UTC).timestamp() + 86_400
                return max(1.0, midnight - datetime.now(UTC).timestamp())
            if self._per_minute:
                rate = self._per_minute / 60.0
                self._tokens = min(float(self._per_minute), self._tokens + (now - self._refilled_at) * rate)
                self._refilled_at = now
                if self._tokens < 1.0:
                    return (1.0 - self._tokens) / rate
                self._tokens -= 1.0
            self._used_today += 1
            return None

    def reset(self) -> None:
        with self._lock:
            self._tokens = float(self._per_minute)
            self._refilled_at = self._clock()
            self._day, self._used_today = self._today(), 0
