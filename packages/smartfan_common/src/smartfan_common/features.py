"""Reference causal feature extraction, identical for batch and live consumers.

No labels, equipment IDs, latent damage or future values enter the vector.
This bounded reference implementation can validate a later NumPy optimization.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from statistics import fmean, pstdev
from typing import Iterable, Iterator, Literal

from .contracts import TelemetryEvent

FEATURE_VERSION = "hvac-window-v1"
SENSORS = (
    "current_a",
    "compressor_case_temp_c",
    "vibration_rms_mm_s",
    "indoor_temp_c",
    "outdoor_temp_c",
)
FEATURE_NAMES = tuple(
    f"{sensor}_{stat}" for sensor in SENSORS for stat in ("mean", "std", "slope_per_s")
) + ("case_minus_outdoor_mean", "indoor_cooling_rate_c_per_min", "coverage")


@dataclass(frozen=True)
class FeatureConfig:
    window_seconds: float = 60
    min_span_seconds: float = 30
    min_samples: int = 3
    min_coverage: float = 0.8
    max_gap_seconds: float = 5
    max_samples: int = 300
    max_devices: int = 1000

    def __post_init__(self) -> None:
        for value in (
            self.window_seconds,
            self.min_span_seconds,
            self.min_coverage,
            self.max_gap_seconds,
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError("Window parameters must be finite numbers")
        for value in (self.min_samples, self.max_samples, self.max_devices):
            if type(value) is not int:
                raise ValueError("Capacity parameters must be integers")
        if not (0 < self.min_span_seconds <= self.window_seconds):
            raise ValueError("Invalid window duration")
        if not (2 <= self.min_samples <= self.max_samples):
            raise ValueError("Invalid sample limits")
        if not (0 < self.min_coverage <= 1) or self.max_gap_seconds <= 0:
            raise ValueError("Invalid coverage/gap limits")
        if self.max_devices < 1:
            raise ValueError("Invalid device limit")


@dataclass(frozen=True)
class FeatureResult:
    status: Literal["valid", "warming_up", "insufficient_data", "ignored", "inactive"]
    values: tuple[float, ...] | None = None


@dataclass
class _Window:
    boot_id: str
    sequence: int
    timestamp: float
    compressor_on: bool
    samples: deque[tuple[float, tuple[float | None, ...]]]


def _slope(points: list[tuple[float, float]]) -> float:
    times = [t - points[0][0] for t, _ in points]
    mean_t = fmean(times)
    mean_y = fmean(v for _, v in points)
    denominator = sum((t - mean_t) ** 2 for t in times)
    if denominator == 0:
        return 0.0
    return sum((t - mean_t) * (p[1] - mean_y) for t, p in zip(times, points)) / denominator


class FeatureWindow:
    def __init__(self, config: FeatureConfig | None = None):
        self.config = config or FeatureConfig()
        self._devices: dict[str, _Window] = {}

    def push(self, event: TelemetryEvent) -> FeatureResult:
        timestamp = datetime.fromisoformat(event.timestamp).timestamp()
        window = self._devices.get(event.device_id)
        if window is not None:
            if timestamp <= window.timestamp:
                return FeatureResult("ignored")
            if (
                window.boot_id == event.metadata.boot_id
                and event.metadata.sequence <= window.sequence
            ):
                return FeatureResult("ignored")
        if window is None:
            if len(self._devices) >= self.config.max_devices:
                raise ValueError("Device capacity exhausted")
            window = _Window(
                event.metadata.boot_id,
                -1,
                timestamp,
                event.data.actuators.compressor_on,
                deque(maxlen=self.config.max_samples),
            )
            self._devices[event.device_id] = window
        if (
            window.boot_id != event.metadata.boot_id
            or timestamp - window.timestamp > self.config.max_gap_seconds
            or window.compressor_on != event.data.actuators.compressor_on
        ):
            window.samples.clear()
        window.boot_id = event.metadata.boot_id
        window.sequence = event.metadata.sequence
        window.timestamp = timestamp
        window.compressor_on = event.data.actuators.compressor_on
        if not window.compressor_on:
            window.samples.clear()
            return FeatureResult("inactive")
        readings = tuple(getattr(event.data.readings, sensor) for sensor in SENSORS)
        window.samples.append((timestamp, readings))
        while window.samples and timestamp - window.samples[0][0] > self.config.window_seconds:
            window.samples.popleft()
        if (
            len(window.samples) < self.config.min_samples
            or timestamp - window.samples[0][0] < self.config.min_span_seconds
        ):
            return FeatureResult("warming_up")
        features: list[float] = []
        coverages: list[float] = []
        indoor_slope = 0.0
        for index, sensor in enumerate(SENSORS):
            points = [(t, v[index]) for t, v in window.samples if v[index] is not None]
            present: list[tuple[float, float]] = [(t, float(v)) for t, v in points if v is not None]
            coverage = len(present) / len(window.samples)
            if len(present) < self.config.min_samples or coverage < self.config.min_coverage:
                return FeatureResult("insufficient_data")
            values = [v for _, v in present]
            slope = _slope(present)
            features.extend([fmean(values), pstdev(values), slope])
            coverages.append(coverage)
            if sensor == "indoor_temp_c":
                indoor_slope = slope
        deltas = [
            float(v[1]) - float(v[4])
            for _, v in window.samples
            if v[1] is not None and v[4] is not None
        ]
        if not deltas:
            return FeatureResult("insufficient_data")
        features.extend([fmean(deltas), -indoor_slope * 60, min(coverages)])
        return FeatureResult("valid", tuple(features))

    def forget(self, device_id: str) -> None:
        """Release a disabled device explicitly; do not evict active devices silently."""
        self._devices.pop(device_id, None)


def iter_features(
    events: Iterable[TelemetryEvent], config: FeatureConfig | None = None
) -> Iterator[FeatureResult]:
    """Bounded-memory batch reference; retain one window across input chunks."""
    window = FeatureWindow(config)
    for event in events:
        yield window.push(event)


def extract_batch(
    events: Iterable[TelemetryEvent], config: FeatureConfig | None = None
) -> list[FeatureResult]:
    """Small-dataset convenience; mass generation should consume iter_features."""
    return list(iter_features(events, config))
