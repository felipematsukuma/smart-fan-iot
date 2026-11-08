"""Validated REST and MQTT contracts; telemetry timestamps are device uptime in ms."""

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

DeviceId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)]


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
    device_epoch_s: NonNegative | None = None
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
    voltage_rms: Annotated[float, Field(ge=0, le=1000, allow_inf_nan=False, strict=True)]
    current_a: Annotated[float, Field(ge=0, le=1000, allow_inf_nan=False, strict=True)]
    power_w: Annotated[float, Field(ge=0, le=1000000, allow_inf_nan=False, strict=True)]
    timestamp: NonNegative


class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: DeviceId
    name: Annotated[str, Field(min_length=1, max_length=100)]


class DeviceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: DeviceId
    name: str
    is_on: bool
    kwh_rate: NonNegative
    auto_off_time: str | None
    auto_off_enabled: bool


class MetricPoint(BaseModel):
    time: datetime
    power_w: NonNegative


class SeriesSegment(BaseModel):
    kind: Literal["active", "off", "no-data"]
    from_: datetime = Field(alias="from")
    to: datetime


class MetricsView(BaseModel):
    device_id: DeviceId
    period_start: datetime
    period_end: datetime
    duration_hours: NonNegative
    avg_power_w: NonNegative
    energy_wh: NonNegative
    estimated_kwh: NonNegative
    history_count: int
    history: list[MetricPoint]
    coverage: Annotated[float, Field(ge=0, le=1)]
    covered_seconds: NonNegative
    max_power_w: NonNegative
    segments: list[SeriesSegment]
