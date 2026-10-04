"""Retry logic with exponential backoff and jitter."""

from __future__ import annotations

import random
import time


class RetryManager:
    """Manages transmission backoff states."""

    def __init__(
        self,
        base_backoff_seconds: float = 0.5,
        max_backoff_seconds: float = 30.0,
        jitter_factor: float = 0.25,
    ) -> None:
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.jitter_factor = jitter_factor
        self.consecutive_failures = 0
        self.last_failure_time: float | None = None
        self.total_retries = 0

    def record_success(self) -> None:
        """Reset failure counter upon successful transmission."""
        self.consecutive_failures = 0

    def record_failure(self) -> float:
        """Record transmission failure and compute sleep duration with backoff and jitter."""
        self.consecutive_failures += 1
        self.total_retries += 1
        self.last_failure_time = time.time()

        # Exponential backoff: base * 2^(failures - 1)
        raw_backoff = self.base_backoff_seconds * (2 ** min(self.consecutive_failures - 1, 8))
        capped_backoff = min(raw_backoff, self.max_backoff_seconds)

        # Apply random jitter
        jitter_range = capped_backoff * self.jitter_factor
        jitter = random.uniform(-jitter_range, jitter_range)
        sleep_duration = max(0.1, capped_backoff + jitter)
        return sleep_duration
