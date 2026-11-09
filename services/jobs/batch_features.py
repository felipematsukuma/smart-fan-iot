"""Select causal windows, then invoke the exact installed streaming feature kernel."""

from collections import Counter
from dataclasses import asdict
from pathlib import Path

import numpy as np
from smartfan_common.features import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    SENSORS,
    FeatureConfig,
    summarize_window,
)


def extract(
    path: Path, manifest: dict, limit: int, seed: int, cancel=lambda: False
) -> dict:
    content = manifest["content"]
    count = content["rows"]
    channels = content["channels"]
    primary = content["primary_channel_indices"]
    if len(primary) != 5 or [channels[index]["field"] for index in primary] != list(
        SENSORS
    ):
        raise ValueError("Dataset has incompatible primary channels")
    observed = np.load(path / "readings.npy", mmap_mode="r", allow_pickle=False)
    stamps = np.load(path / "timestamp_seconds.npy", mmap_mode="r", allow_pickle=False)
    on = np.load(path / "compressor_on.npy", mmap_mode="r", allow_pickle=False)
    groups = np.load(path / "equipment_index.npy", mmap_mode="r", allow_pickle=False)
    health = np.load(path / "health_score.npy", mmap_mode="r", allow_pickle=False)
    rul = np.load(path / "rul_calendar_hours.npy", mmap_mode="r", allow_pickle=False)
    if observed.shape != (count, len(channels)) or observed.dtype != np.dtype("<f4"):
        raise ValueError("Invalid observations shape")
    equipment_count = len(content["devices"])
    per_device = count // equipment_count
    if per_device * equipment_count != count:
        raise ValueError("Uneven dataset groups")
    config = FeatureConfig()
    vectors = []
    targets = []
    identities = []
    modes = []
    indices = []
    statuses: Counter[str] = Counter()
    take = max(1, limit // equipment_count)
    for device in range(equipment_count):
        if cancel():
            raise InterruptedError("Training cancelled")
        start = device * per_device
        end = start + per_device
        if not np.all(groups[start:end] == device):
            raise ValueError("Equipment groups overlap")
        times = stamps[start:end]
        running = on[start:end]
        gaps = np.diff(times)
        if np.any(gaps <= 0):
            raise ValueError("Noncausal dataset chronology")
        split = np.r_[
            True, (gaps > config.max_gap_seconds) | (running[1:] != running[:-1])
        ]
        run_start = np.maximum.accumulate(np.where(split, np.arange(per_device), 0))
        rng = np.random.default_rng(np.random.SeedSequence([seed, device]))
        selected = np.sort(
            rng.choice(per_device, size=min(take, per_device), replace=False)
        )
        for index in selected:
            if cancel():
                raise InterruptedError("Training cancelled")
            if not running[index]:
                statuses["inactive"] += 1
                continue
            first = max(
                int(run_start[index]),
                int(
                    np.searchsorted(
                        times, times[index] - config.window_seconds, side="left"
                    )
                ),
            )
            values = observed[start + first : start + index + 1][:, primary]
            samples = [
                (
                    float(stamp),
                    tuple(
                        float(value) if np.isfinite(value) else None for value in row
                    ),
                )
                for stamp, row in zip(times[first : index + 1], values, strict=True)
            ]
            result = summarize_window(samples, at=float(times[index]), config=config)
            statuses[result.status] += 1
            if result.status != "valid":
                continue
            vectors.append(result.values)
            targets.append((float(health[start + index]), float(rul[start + index])))
            identities.append(device)
            modes.append(content["devices"][device]["failure_mode"])
            indices.append(start + int(index))
    if len(vectors) < 100:
        raise ValueError("Insufficient causal feature rows")
    return {
        "X": np.asarray(vectors, dtype=np.float64),
        "y": np.asarray(targets, dtype=np.float64),
        "groups": np.asarray(identities, dtype=np.int32),
        "modes": np.asarray(modes, dtype="U24"),
        "source_indices": np.asarray(indices, dtype=np.int64),
        "statuses": dict(statuses),
        "feature_config": asdict(config),
        "feature_names": list(FEATURE_NAMES),
        "feature_version": FEATURE_VERSION,
    }
