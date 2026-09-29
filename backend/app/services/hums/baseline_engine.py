"""H3: Baseline statistics — pure functions over a list of historical
feature values. No DB access; app.services.hums.baseline_service owns
turning these into persisted HUMSBaseline rows.
"""

from __future__ import annotations

import dataclasses
import math
import statistics
from typing import Literal

BaselineQuality = Literal["VALID", "LIMITED", "INSUFFICIENT_DATA", "STALE", "INVALID"]
Confidence = Literal["HIGH", "MEDIUM", "LOW", "INSUFFICIENT_DATA"]

# Sample-count thresholds. Deliberately small, documented constants (not a
# "real" statistical power calculation) — see docs/HUMS_BASELINE_ENGINE.md.
MIN_SAMPLES_FOR_BASELINE = 5     # below this: INSUFFICIENT_DATA, no baseline at all
LIMITED_SAMPLES_THRESHOLD = 15   # below this: LIMITED quality, still usable but low confidence
GOOD_SAMPLES_THRESHOLD = 30      # at/above this: VALID quality, HIGH confidence


@dataclasses.dataclass(frozen=True)
class BaselineStats:
    sample_count: int
    mean: float
    median: float
    std_dev: float
    minimum: float
    maximum: float
    percentile_05: float
    percentile_25: float
    percentile_50: float
    percentile_75: float
    percentile_95: float
    lower_bound: float
    upper_bound: float
    quality: BaselineQuality
    confidence: Confidence
    calculation_method: str


def _percentile(sorted_values: list[float], pct: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]
    idx = min(len(sorted_values) - 1, max(0, math.ceil(pct * len(sorted_values)) - 1))
    return sorted_values[idx]


def compute_baseline_stats(values: list[float]) -> BaselineStats | None:
    """Computes robust-percentile baseline statistics.

    Returns None (no baseline can be established) if fewer than
    MIN_SAMPLES_FOR_BASELINE valid values are provided — callers must not
    invent a baseline from too little history.

    `lower_bound`/`upper_bound` use the 5th/95th percentile (robust to
    outliers) rather than mean ± N*std, documented as the chosen method in
    `calculation_method` so a caller can tell which convention was used.
    """
    n = len(values)
    if n < MIN_SAMPLES_FOR_BASELINE:
        return None

    sorted_vals = sorted(values)
    mean = statistics.mean(values)
    median = statistics.median(values)
    std_dev = statistics.pstdev(values)

    if n >= GOOD_SAMPLES_THRESHOLD:
        quality: BaselineQuality = "VALID"
        confidence: Confidence = "HIGH"
    elif n >= LIMITED_SAMPLES_THRESHOLD:
        quality = "LIMITED"
        confidence = "MEDIUM"
    else:
        quality = "LIMITED"
        confidence = "LOW"

    p05 = _percentile(sorted_vals, 0.05)
    p95 = _percentile(sorted_vals, 0.95)

    return BaselineStats(
        sample_count=n,
        mean=round(mean, 6),
        median=median,
        std_dev=round(std_dev, 6),
        minimum=sorted_vals[0],
        maximum=sorted_vals[-1],
        percentile_05=p05,
        percentile_25=_percentile(sorted_vals, 0.25),
        percentile_50=_percentile(sorted_vals, 0.50),
        percentile_75=_percentile(sorted_vals, 0.75),
        percentile_95=p95,
        lower_bound=p05,
        upper_bound=p95,
        quality=quality,
        confidence=confidence,
        calculation_method="percentile_05_95_robust_range",
    )


__all__ = [
    "BaselineStats",
    "compute_baseline_stats",
    "MIN_SAMPLES_FOR_BASELINE",
    "LIMITED_SAMPLES_THRESHOLD",
    "GOOD_SAMPLES_THRESHOLD",
]
