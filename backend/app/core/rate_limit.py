from __future__ import annotations

from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, status


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int = 10, window_seconds: int = 60) -> None:
        now = monotonic()
        threshold = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] < threshold:
                events.popleft()
            if len(events) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="请求过于频繁，请稍后重试",
                )
            events.append(now)


auth_limiter = InMemoryRateLimiter()

