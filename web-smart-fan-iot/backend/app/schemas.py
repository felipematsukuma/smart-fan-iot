"""Validated REST and MQTT contracts; telemetry timestamps are device uptime in ms."""
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

DeviceId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class DeviceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["ON", "OFF"]

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, value):
        return value.upper() if isinstance(value, str) else value


class AutoShutdownUpdate(BaseModel):
    auto_off_time: str
    auto_off_enabled: StrictBool

    @field_validator("auto_off_time")
    @classmethod
    def validate_auto_off_time(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("auto_off_time deve estar no formato HH:MM")
        return value


class TariffUpdate(BaseModel):
    kwh_rate: NonNegative = 0.85


class ScheduleUpdate(AutoShutdownUpdate, TariffUpdate):
    pass


class DeviceState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: DeviceId
    is_on: StrictBool | None = None
    auto_mode: StrictBool | None = None
    shutdown_time: str | None = None
    total_energy_wh: NonNegative | None = None
    fan_on_time_ms: NonNegative | None = None

    @field_validator("shutdown_time")
    @classmethod
    def validate_time(cls, value):
        if value is not None:
            AutoShutdownUpdate.validate_auto_off_time(value)
        return value


class TelemetryPayload(DeviceState):
    is_on: StrictBool
    voltage_rms: Annotated[float, Field(ge=0, le=1000, allow_inf_nan=False)]
    current_a: Annotated[float, Field(ge=0, le=1000, allow_inf_nan=False)]
    power_w: Annotated[float, Field(ge=0, le=1000000, allow_inf_nan=False)]
    timestamp: NonNegative
