"""Sliding-window rate limiter.

Protects partner-facing and login endpoints from bursts and brute force. State
is in-memory (per process). For several API replicas, swap the store for Redis
(`INCR` + `EXPIRE`) - the interface stays the same.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window_seconds:
                q.popleft()
            if len(q) >= limit:
                retry_after = int(window_seconds - (now - q[0])) + 1
                return False, retry_after
            q.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def rate_limit(bucket: str, limit_getter):
    """FastAPI dependency. `limit_getter` is a callable so tests can change limits via settings."""

    def dependency(request: Request) -> None:
        client = request.headers.get("X-API-Key") or (request.client.host if request.client else "unknown")
        allowed, retry_after = limiter.check(f"{bucket}:{client}", limit_getter())
        if not allowed:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

    return dependency
