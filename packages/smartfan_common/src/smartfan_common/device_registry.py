"""Minimal residential on/off split profile, separate from physical observations."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contracts import Identifier, WireModel

DeviceId = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")]


class HealthyRange(WireModel):
    minimum: Annotated[float, Field(allow_inf_nan=False, ge=-50, le=150)]
    maximum: Annotated[float, Field(allow_inf_nan=False, ge=-50, le=150)]

    @model_validator(mode="after")
    def ordered(self) -> "HealthyRange":
        if self.minimum >= self.maximum:
            raise ValueError("Range must increase")
        return self


class HealthyRanges(WireModel):
    current_a: HealthyRange = Field(default_factory=lambda: HealthyRange(minimum=0, maximum=12))
    compressor_case_temp_c: HealthyRange = Field(
        default_factory=lambda: HealthyRange(minimum=15, maximum=75)
    )
    vibration_rms_mm_s: HealthyRange = Field(
        default_factory=lambda: HealthyRange(minimum=0, maximum=3)
    )
    indoor_temp_c: HealthyRange = Field(
        default_factory=lambda: HealthyRange(minimum=20, maximum=28)
    )
    outdoor_temp_c: HealthyRange = Field(
        default_factory=lambda: HealthyRange(minimum=15, maximum=40)
    )

    @model_validator(mode="after")
    def physical_ranges(self) -> "HealthyRanges":
        if self.current_a.minimum < 0 or self.current_a.maximum > 50:
            raise ValueError("Invalid current range in amperes")
        if self.vibration_rms_mm_s.minimum < 0 or self.vibration_rms_mm_s.maximum > 50:
            raise ValueError("Invalid vibration range in mm/s")
        return self


class DeviceProfile(WireModel):
    healthy_ranges: HealthyRanges = Field(default_factory=HealthyRanges)
    nominal_voltage_v: Annotated[int, Field(strict=True, ge=110, le=240)] = 220
    rated_power_w: Annotated[float, Field(gt=0, le=10000, allow_inf_nan=False)] = 1000
    expected_life_hours: Annotated[int, Field(strict=True, ge=1000, le=200000)] = 30000


class DeviceCreate(WireModel):
    id: DeviceId
    name: Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$")]
    zone: Identifier
    equipment_type: Literal["ac_split_onoff"] = "ac_split_onoff"
    profile: DeviceProfile = Field(default_factory=DeviceProfile)


class DeviceUpdate(WireModel):
    expected_revision: Annotated[int, Field(strict=True, ge=1)]
    name: (
        Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f\x7f]+$")] | None
    ) = None
    enabled: Annotated[bool, Field(strict=True)] | None = None
    profile: DeviceProfile | None = None

    @model_validator(mode="after")
    def nonempty(self) -> "DeviceUpdate":
        fields = self.model_fields_set - {"expected_revision"}
        if not fields or any(getattr(self, key) is None for key in fields):
            raise ValueError("Provide non-null changes")
        return self
