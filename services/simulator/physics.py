"""Small, explicit simulation hypotheses; not a calibrated appliance model."""

import math
import random
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PlantConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    scenario: Literal["healthy", "mechanical_wear", "heat_transfer_loss"] = "healthy"
    initial_damage: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    damage_per_operating_hour: float = Field(
        default=0.00005, ge=0, le=60, allow_inf_nan=False
    )
    ambient_mean_c: float = Field(default=30, ge=15, le=45, allow_inf_nan=False)
    ambient_amplitude_c: float = Field(default=5, ge=0, le=10, allow_inf_nan=False)
    noise: float = Field(default=0.03, ge=0, le=0.2, allow_inf_nan=False)
    voltage_v: float = Field(default=220, ge=100, le=250, allow_inf_nan=False)
    power_factor: float = Field(default=0.93, gt=0, le=1, allow_inf_nan=False)


class PlantState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)
    indoor_temp_c: float = Field(default=27, ge=-20, le=80, allow_inf_nan=False)
    case_temp_c: float = Field(default=32, ge=-20, le=200, allow_inf_nan=False)
    damage: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    operating_hours: float = Field(default=0, ge=0, allow_inf_nan=False)
    ticks: int = Field(default=0, ge=0)
    compressor_on: bool = False
    condenser_fan_on: bool = False
    mode: Literal["manual", "auto"] = "auto"
    manual_cooling_block: bool = False
    thermal_lock: bool = False
    last_off_epoch: float = Field(default=-1e12, allow_inf_nan=False)
    last_revision: int = Field(default=0, ge=0)
    reason_code: str = "boot_safe_off"


def advance(
    state: PlantState, config: PlantConfig, epoch: float, elapsed: float
) -> dict[str, float]:
    if (
        not math.isfinite(epoch)
        or not math.isfinite(elapsed)
        or not 0 <= elapsed <= 3600
    ):
        raise ValueError("Invalid physical simulation step")
    local_hour = (epoch / 3600 - 3) % 24
    day = datetime.fromtimestamp(epoch, UTC).timetuple().tm_yday
    outside = (
        config.ambient_mean_c
        + config.ambient_amplitude_c * math.cos(2 * math.pi * (local_hour - 15) / 24)
        + 0.6 * math.cos(2 * math.pi * (day - 15) / 365)
    )
    if state.compressor_on and not state.condenser_fan_on:
        state.compressor_on = False
        state.last_off_epoch = epoch
        state.reason_code = "local_interlock"
    if state.compressor_on:
        state.operating_hours += elapsed / 3600
        if config.scenario != "healthy":
            state.damage = min(
                1.0, state.damage + config.damage_per_operating_hour * elapsed / 3600
            )
    rng = random.Random(config.seed + state.ticks)
    state.ticks += 1
    damage = state.damage
    case_target = (
        outside
        + 3
        + (20 + 32 * damage + 0.5 * max(0, outside - 25) if state.compressor_on else 0)
    )
    state.case_temp_c += (case_target - state.case_temp_c) * (
        1 - math.exp(-elapsed / (45 if state.condenser_fan_on else 180))
    )
    if state.case_temp_c >= 85:
        state.thermal_lock = True
        if state.compressor_on:
            state.compressor_on = False
            state.last_off_epoch = epoch
            state.reason_code = "local_thermal_protection"
    elif state.case_temp_c < 75:
        state.thermal_lock = False
    cooling_loss = 0.8 if config.scenario == "heat_transfer_loss" else 0.65
    cooling = 0.006 * (1 - cooling_loss * damage) if state.compressor_on else 0
    state.indoor_temp_c = max(
        -20,
        min(
            80,
            state.indoor_temp_c
            + elapsed * (0.0008 + 0.0007 * (outside - state.indoor_temp_c) - cooling),
        ),
    )
    current = (
        4 + 0.05 * max(0, outside - 25) + 2 * damage if state.compressor_on else 0
    ) + (0.18 if state.condenser_fan_on else 0)
    current = max(0, current + rng.gauss(0, config.noise) if current else 0)
    vibration = max(
        0,
        (
            0.8
            + (6 if config.scenario != "heat_transfer_loss" else 1) * damage
            + rng.gauss(0, config.noise)
        )
        if state.compressor_on
        else 0,
    )
    return {
        "current_a": round(current, 4),
        "compressor_case_temp_c": round(
            state.case_temp_c + rng.gauss(0, config.noise), 3
        ),
        "vibration_rms_mm_s": round(vibration, 4),
        "indoor_temp_c": round(state.indoor_temp_c + rng.gauss(0, config.noise), 3),
        "outdoor_temp_c": round(outside + rng.gauss(0, config.noise), 3),
        "power_w": round(current * config.voltage_v * config.power_factor, 3),
    }
