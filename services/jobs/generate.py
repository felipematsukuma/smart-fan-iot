"""Bounded NumPy laboratory generator. No broker/network or live event imports."""

import hashlib
import importlib
import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from smartfan_common.features import SENSORS
from smartfan_common.lab_config import LabConfig


class Cancelled(RuntimeError):
    pass


class Channel(TypedDict):
    field: str
    channel: int
    primary: bool
    position: str


def canonical(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode()


def progress(path: Path, processed: int, total: int) -> None:
    temporary = path / "progress.tmp"
    temporary.write_bytes(canonical({"processed": processed, "total": total}))
    os.replace(temporary, path / "progress.json")


def digest_file(path: Path, cancel) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            if cancel():
                raise Cancelled("cancelled")
            digest.update(block)
    return digest.hexdigest()


def generate(config: LabConfig, path: Path, cancel=lambda: False) -> dict:
    import numpy as np

    started = time.monotonic()
    path.mkdir(parents=True, exist_ok=True)
    channels: list[Channel] = [
        {
            "field": field,
            "channel": index,
            "primary": index == 0,
            "position": f"{field}_point_{index + 1}",
        }
        for field in SENSORS
        for index in range(config.sensor_counts.model_dump()[field])
    ]
    specs = {
        "readings": ("<f4", (config.total, len(channels))),
        "timestamp_seconds": ("<f8", (config.total,)),
        "equipment_index": ("<u2", (config.total,)),
        "compressor_on": ("|b1", (config.total,)),
        "condenser_fan_on": ("|b1", (config.total,)),
        "health_score": ("<f4", (config.total,)),
        "rul_calendar_hours": ("<f4", (config.total,)),
        "censored": ("|b1", (config.total,)),
        "outliers": ("|b1", (config.total, len(channels))),
    }
    arrays = {
        name: np.lib.format.open_memmap(
            path / (name + ".npy"), mode="w+", dtype=dtype, shape=shape
        )
        for name, (dtype, shape) in specs.items()
    }
    devices = []
    n = config.samples_per_equipment
    epoch = datetime.fromisoformat(config.start_utc).timestamp()
    scale = {
        "current_a": 1.0,
        "compressor_case_temp_c": 2.0,
        "vibration_rms_mm_s": 0.3,
        "indoor_temp_c": 1.0,
        "outdoor_temp_c": 1.0,
    }
    bounds = {
        "current_a": (0, 50),
        "compressor_case_temp_c": (-20, 150),
        "vibration_rms_mm_s": (0, 50),
        "indoor_temp_c": (-20, 80),
        "outdoor_temp_c": (-20, 80),
    }
    for device_index in range(config.equipment_count):
        rng = np.random.default_rng(
            np.random.SeedSequence([config.seed, device_index, 65535])
        )
        failing = bool(rng.random() < config.failure_fraction)
        mode = (
            config.failure_modes[int(rng.integers(0, len(config.failure_modes)))]
            if failing
            else "healthy"
        )
        duration = config.days * 86400
        onset = float(rng.uniform(0.05, 0.4) * duration)
        failure_time = (
            float(rng.uniform(0.65, 1.5) * duration) if failing else float("inf")
        )
        censored = failure_time > duration
        ambient = float(rng.uniform(27, 34))
        phase = float(rng.uniform(0, 2 * np.pi))
        cycle = float(rng.uniform(2400, 4800))
        duty = float(rng.uniform(0.5, 0.8))
        devices.append(
            {
                "id": f"lab_ac_{device_index:04d}",
                "equipment_index": device_index,
                "failure_mode": mode,
                "failure_observed": not censored,
                "failure_seconds": failure_time if not censored else None,
                "sensor_ids": [
                    f"lab_ac_{device_index:04d}_{channel['field']}_{channel['channel'] + 1}"
                    for channel in channels
                ],
            }
        )
        noise = [
            np.random.default_rng(
                np.random.SeedSequence([config.seed, device_index, j, 0])
            )
            for j in range(len(channels))
        ]
        missing = [
            np.random.default_rng(
                np.random.SeedSequence([config.seed, device_index, j, 1])
            )
            for j in range(len(channels))
        ]
        outlier = [
            np.random.default_rng(
                np.random.SeedSequence([config.seed, device_index, j, 2])
            )
            for j in range(len(channels))
        ]
        impulses = [
            np.random.default_rng(
                np.random.SeedSequence([config.seed, device_index, j, 3])
            )
            for j in range(len(channels))
        ]
        for start in range(0, n, config.block_size):
            if cancel():
                raise Cancelled("cancelled")
            end = min(n, start + config.block_size)
            offset = device_index * n
            target = slice(offset + start, offset + end)
            seconds = (
                np.arange(start, end, dtype=np.float64) * config.sample_interval_seconds
            )
            damage = (
                np.clip((seconds - onset) / (failure_time - onset), 0, 1)
                if failing
                else np.zeros(end - start)
            )
            operating = (
                np.remainder(seconds + phase * cycle, cycle) < cycle * duty
            ) & (damage < 1)
            fan = operating | (
                (np.remainder(seconds + phase * cycle, cycle) < cycle * duty + 120)
                & (damage < 1)
            )
            outside = ambient + 5 * np.cos(
                2 * np.pi * ((seconds / 3600 - 3) % 24 - 15) / 24
            )
            indoor = (
                24
                + 1.2 * np.sin(2 * np.pi * seconds / cycle + phase)
                + 0.12 * (outside - 30)
                + damage * (3 if mode == "heat_transfer_loss" else 1)
            )
            current = (
                operating * (4 + 0.05 * np.maximum(0, outside - 25) + 2 * damage)
                + fan * 0.18
            )
            case = (
                outside
                + 3
                + operating * (20 + 32 * damage + 0.5 * np.maximum(0, outside - 25))
            )
            vibration = operating * (
                0.8 + (6 if mode == "mechanical_wear" else 1) * damage
            )
            observed = {
                "current_a": current,
                "compressor_case_temp_c": case,
                "vibration_rms_mm_s": vibration,
                "indoor_temp_c": indoor,
                "outdoor_temp_c": outside,
            }
            for channel_index, channel in enumerate(channels):
                field = channel["field"]
                values = (
                    observed[field]
                    + noise[channel_index].normal(
                        0, config.noise_std * scale[field], end - start
                    )
                    + channel["channel"] * 0.015 * scale[field]
                )
                corrupt = (
                    outlier[channel_index].random(end - start) < config.outlier_fraction
                )
                # Independent stream keeps block partitioning reproducible.
                values += corrupt * impulses[channel_index].normal(
                    0, 8 * scale[field], end - start
                )
                values = np.clip(values, *bounds[field])
                absent = (
                    missing[channel_index].random(end - start) < config.missing_fraction
                )
                values[absent] = np.nan
                arrays["readings"][target, channel_index] = values
                arrays["outliers"][target, channel_index] = corrupt
            arrays["timestamp_seconds"][target] = epoch + seconds
            arrays["equipment_index"][target] = device_index
            arrays["compressor_on"][target] = operating
            arrays["condenser_fan_on"][target] = fan
            arrays["health_score"][target] = 100 * (1 - damage)
            arrays["rul_calendar_hours"][target] = (
                np.nan if censored else np.maximum(0, failure_time - seconds) / 3600
            )
            arrays["censored"][target] = censored
            for array in arrays.values():
                array.flush()
            progress(path, offset + end, config.total)
    for array in arrays.values():
        array.flush()
    arrays.clear()
    files = {
        name + ".npy": digest_file(path / (name + ".npy"), cancel) for name in specs
    }
    content = {
        "format_version": 1,
        "generator_version": config.generator_version,
        "numpy_version": np.__version__,
        "configuration": config.model_dump(exclude={"block_size"}),
        "rows": config.total,
        "channels": channels,
        "primary_channel_indices": [
            i for i, channel in enumerate(channels) if channel["primary"]
        ],
        "devices": devices,
        "files": files,
        "rul_unit": "calendar_hours",
        "truth_scope": "lab_only",
        "censor_policy": "rul_is_nan_when_failure_not_observed",
        "physics": "didactic_quasisteady_split_onoff_v1",
    }
    manifest = {
        "content": content,
        "sha256": hashlib.sha256(canonical(content)).hexdigest(),
        "execution": {
            "seconds": time.monotonic() - started,
            "block_size": config.block_size,
            "peak_rss_mib": importlib.import_module("resource").getrusage(0).ru_maxrss
            / 1024
            if os.name == "posix"
            else None,
        },
    }
    (path / "manifest.json").write_bytes(canonical(manifest))
    return manifest


def main() -> None:
    from .child_guard import supervise_parent

    path = Path(sys.argv[1])
    supervise_parent(path)
    cancelled = False

    def stop(*_):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    config = LabConfig.model_validate_json((path / "config.json").read_bytes())
    try:
        generate(
            config, path, lambda: cancelled or (path / "cancel.requested").exists()
        )
    except Cancelled:
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
