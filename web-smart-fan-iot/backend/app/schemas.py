import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class DeviceCommand(BaseModel):
    action: Literal["ON", "OFF"]
    speed: int = Field(default=1, ge=1, le=3)

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, value):
        return value.upper() if isinstance(value, str) else value


class ScheduleUpdate(BaseModel):
    auto_off_time: str
    auto_off_enabled: bool
    kwh_rate: float = Field(default=0.85, ge=0)

    @field_validator("auto_off_time")
    @classmethod
    def validate_auto_off_time(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("auto_off_time deve estar no formato HH:MM")
        return value


class AutoShutdownUpdate(BaseModel):
    auto_off_time: str
    auto_off_enabled: bool

    @field_validator("auto_off_time")
    @classmethod
    def validate_auto_off_time(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("auto_off_time deve estar no formato HH:MM")
        return value


class TariffUpdate(BaseModel):
    kwh_rate: float = Field(default=0.85, ge=0)


class TelemetryPayload(BaseModel):
    device_id: str
    is_on: bool
    voltage_rms: float
    current_a: float
    power_w: float
    timestamp: float
