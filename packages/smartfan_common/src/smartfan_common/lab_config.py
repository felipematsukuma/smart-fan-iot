"""Immutable laboratory configuration; latent truth is never a live wire contract."""

import math
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import WireModel
from .contracts_v2 import UTC

FailureMode = Literal["mechanical_wear", "heat_transfer_loss"]


def default_modes() -> list[FailureMode]:
    return ["mechanical_wear", "heat_transfer_loss"]


class SensorCounts(WireModel):
    current_a: Annotated[int, Field(strict=True, ge=1, le=4)] = 1
    compressor_case_temp_c: Annotated[int, Field(strict=True, ge=1, le=4)] = 1
    vibration_rms_mm_s: Annotated[int, Field(strict=True, ge=1, le=4)] = 1
    indoor_temp_c: Annotated[int, Field(strict=True, ge=1, le=4)] = 1
    outdoor_temp_c: Annotated[int, Field(strict=True, ge=1, le=4)] = 1

    @property
    def total(self) -> int:
        return sum(
            (
                self.current_a,
                self.compressor_case_temp_c,
                self.vibration_rms_mm_s,
                self.indoor_temp_c,
                self.outdoor_temp_c,
            )
        )


class LabConfig(WireModel):
    generator_version: Literal["hvac-lab-v1"] = "hvac-lab-v1"
    days: Annotated[float, Field(ge=0.01, le=365, allow_inf_nan=False)] = 2.0
    equipment_count: Annotated[int, Field(strict=True, ge=3, le=1000)] = 30
    sensor_counts: SensorCounts = Field(default_factory=SensorCounts)
    sample_interval_seconds: Literal[1, 2, 5] = 5
    seed: Annotated[int, Field(strict=True, ge=0, le=2**31 - 1)] = 42
    failure_fraction: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] = 0.7
    failure_modes: list[FailureMode] = Field(
        default_factory=default_modes,
        min_length=1,
        max_length=2,
    )
    noise_std: Annotated[float, Field(ge=0, le=0.2, allow_inf_nan=False)] = 0.03
    missing_fraction: Annotated[float, Field(ge=0, le=0.2, allow_inf_nan=False)] = 0.01
    outlier_fraction: Annotated[float, Field(ge=0, le=0.1, allow_inf_nan=False)] = 0.005
    block_size: Annotated[int, Field(strict=True, ge=100, le=50000)] = 50000
    records_cap: Annotated[int, Field(strict=True, ge=1, le=5000000)] = 5000000
    start_utc: UTC = "2026-01-01T00:00:00Z"

    @property
    def samples_per_equipment(self) -> int:
        return math.floor(self.days * 86400 / self.sample_interval_seconds)

    @property
    def total(self) -> int:
        return self.samples_per_equipment * self.equipment_count

    @property
    def estimated_bytes(self) -> int:
        # Arrays plus headers/manifest, with a conservative working-space margin.
        return self.total * (48 + self.sensor_counts.total * 6) + 1048576

    @model_validator(mode="after")
    def limits(self) -> "LabConfig":
        if type(self.sample_interval_seconds) is not int:
            raise ValueError("Interval must be an integer")
        if self.total > self.records_cap or self.total < 1:
            raise ValueError("Dataset exceeds configured row cap")
        if len(set(self.failure_modes)) != len(self.failure_modes):
            raise ValueError("Failure modes must be unique")
        return self
