"""In-process request metrics: volume, error counts, latency percentiles, uptime.

Kept deliberately simple (no external dependency) so the dashboard can show
API request volume and response times. In a multi-instance production setup
this would be replaced by Prometheus/OpenTelemetry - see the DevOps handbook.
"""
from __future__ import annotations

import threading
import time
from collections import Counter, deque

START_TIME = time.time()


class Metrics:
    def __init__(self, window: int = 5000):
        self._lock = threading.Lock()
        self.requests = Counter()  # key: "METHOD path_template"
        self.status_classes = Counter()  # "2xx", "4xx", "5xx"
        self.latencies: deque[float] = deque(maxlen=window)
        self.total = 0

    def record(self, method: str, path: str, status: int, duration_ms: float) -> None:
        with self._lock:
            self.total += 1
            self.requests[f"{method} {path}"] += 1
            self.status_classes[f"{status // 100}xx"] += 1
            self.latencies.append(duration_ms)

    def snapshot(self) -> dict:
        with self._lock:
            lat = sorted(self.latencies)

            def pct(p: float) -> float:
                if not lat:
                    return 0.0
                return round(lat[min(len(lat) - 1, int(len(lat) * p))], 2)

            uptime = time.time() - START_TIME
            return {
                "uptime_seconds": round(uptime, 1),
                "total_requests": self.total,
                "status_classes": dict(self.status_classes),
                "error_rate": round(self.status_classes.get("5xx", 0) / self.total, 4) if self.total else 0.0,
                "latency_ms": {"p50": pct(0.5), "p95": pct(0.95), "p99": pct(0.99)},
                "top_endpoints": [{"endpoint": k, "count": v} for k, v in self.requests.most_common(10)],
            }

    def reset(self) -> None:
        with self._lock:
            self.requests.clear()
            self.status_classes.clear()
            self.latencies.clear()
            self.total = 0


metrics = Metrics()
