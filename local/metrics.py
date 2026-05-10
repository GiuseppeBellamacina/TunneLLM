"""Request metrics collection — tokens/sec, latency, TTFT."""

import threading
import time
from dataclasses import dataclass, field


@dataclass
class RequestMetric:
    """Tracks a single inference request."""

    request_id: str
    model: str
    endpoint: str
    start_time: float = field(default_factory=time.time)
    first_token_time: float | None = None
    end_time: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    status: str = "in_progress"  # in_progress | completed | failed
    error: str | None = None

    # ── derived helpers ─────────────────────────────────────

    @property
    def latency(self) -> float | None:
        if self.end_time:
            return self.end_time - self.start_time
        return None

    @property
    def ttft(self) -> float | None:
        if self.first_token_time:
            return self.first_token_time - self.start_time
        return None

    @property
    def tokens_per_sec(self) -> float | None:
        lat = self.latency
        if lat and lat > 0 and self.completion_tokens > 0:
            return self.completion_tokens / lat
        return None


class MetricsCollector:
    """Thread-safe metrics collector with rolling history."""

    def __init__(self, max_history: int = 500) -> None:
        self._history: list[RequestMetric] = []
        self._lock = threading.Lock()
        self._max = max_history

    def new_request(self, request_id: str, model: str, endpoint: str) -> RequestMetric:
        m = RequestMetric(request_id=request_id, model=model, endpoint=endpoint)
        with self._lock:
            self._history.append(m)
            if len(self._history) > self._max:
                self._history = self._history[-self._max :]
        return m

    def get_summary(self) -> dict:
        with self._lock:
            history = list(self._history)

        completed = [m for m in history if m.status == "completed"]
        failed = [m for m in history if m.status == "failed"]

        stats: dict = {
            "total_requests": len(history),
            "completed": len(completed),
            "failed": len(failed),
            "in_progress": len(history) - len(completed) - len(failed),
        }

        if not completed:
            return stats

        latencies = [m.latency for m in completed if m.latency is not None]
        ttfts = [m.ttft for m in completed if m.ttft is not None]
        tps_list = [m.tokens_per_sec for m in completed if m.tokens_per_sec is not None]

        stats["avg_latency_s"] = (
            round(sum(latencies) / len(latencies), 3) if latencies else None
        )
        stats["avg_first_token_s"] = (
            round(sum(ttfts) / len(ttfts), 3) if ttfts else None
        )
        stats["avg_tokens_per_sec"] = (
            round(sum(tps_list) / len(tps_list), 1) if tps_list else None
        )
        stats["total_prompt_tokens"] = sum(m.prompt_tokens for m in completed)
        stats["total_completion_tokens"] = sum(m.completion_tokens for m in completed)

        # Last N requests for quick inspection
        stats["recent"] = [
            {
                "model": m.model,
                "endpoint": m.endpoint,
                "latency_s": round(m.latency, 2) if m.latency else None,
                "first_token_s": round(m.ttft, 2) if m.ttft else None,
                "tokens_per_sec": (
                    round(m.tokens_per_sec, 1) if m.tokens_per_sec else None
                ),
                "prompt_tokens": m.prompt_tokens,
                "completion_tokens": m.completion_tokens,
            }
            for m in completed[-10:]
        ]

        return stats


metrics = MetricsCollector()
