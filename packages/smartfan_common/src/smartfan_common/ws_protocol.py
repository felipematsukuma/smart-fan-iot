"""WebSocket control packets; domain events keep their existing v2 envelope."""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from .contracts import Identifier, UUIDString, WireModel
from .contracts_v2 import UTC, EventV2


class SensorIds(WireModel):
    current_a: Identifier
    compressor_case_temp_c: Identifier
    vibration_rms_mm_s: Identifier
    indoor_temp_c: Identifier
    outdoor_temp_c: Identifier


class ActuatorIds(WireModel):
    compressor_on: Identifier
    condenser_fan_on: Identifier


class DeviceDescriptor(WireModel):
    id: Identifier
    name: Annotated[str, Field(min_length=1, max_length=80)]
    zone: Identifier
    equipment_type: Literal["ac_split_onoff"] = "ac_split_onoff"
    enabled: Annotated[bool, Field(strict=True)] = True
    sensor_ids: SensorIds
    actuator_ids: ActuatorIds
    boot_id: UUIDString | None
    last_sample_at: UTC | None


def default_descriptor(
    device_id: str, zone: str, boot_id: str | None, last_sample_at: str | None
) -> DeviceDescriptor:
    if len(device_id) > 32:
        raise ValueError("Default profile requires a device identifier of at most 32 characters")
    return DeviceDescriptor.model_validate(
        {
            "id": device_id,
            "name": "Ar-condicionado " + device_id,
            "zone": zone,
            "boot_id": boot_id,
            "last_sample_at": last_sample_at,
            "sensor_ids": {
                "current_a": device_id + "_current",
                "compressor_case_temp_c": device_id + "_case_temp",
                "vibration_rms_mm_s": device_id + "_vibration",
                "indoor_temp_c": device_id + "_indoor_temp",
                "outdoor_temp_c": device_id + "_outdoor_temp",
            },
            "actuator_ids": {
                "compressor_on": device_id + "_compressor",
                "condenser_fan_on": device_id + "_condenser_fan",
            },
        }
    )


class TicketRequest(WireModel):
    devices: list[Identifier] | None = Field(default=None, max_length=100)


class Authenticate(WireModel):
    type: Literal["authenticate"]
    ticket: Annotated[str, Field(strict=True, min_length=32, max_length=128, repr=False)]
    devices: list[Identifier] | None = Field(default=None, max_length=100)


class Subscribe(WireModel):
    type: Literal["subscribe"]
    devices: list[Identifier] = Field(max_length=100)


class Ping(WireModel):
    type: Literal["ping"]
    id: UUIDString


class Pong(WireModel):
    type: Literal["pong"]
    id: UUIDString


class Authenticated(WireModel):
    type: Literal["authenticated"] = "authenticated"
    server_time: UTC
    heartbeat_seconds: Literal[15] = 15
    stale_after_seconds: Literal[6] = 6


class Snapshot(WireModel):
    type: Literal["snapshot"] = "snapshot"
    server_time: UTC
    devices: list[DeviceDescriptor] = Field(max_length=100)
    events: list[EventV2] = Field(max_length=300)


class Notice(WireModel):
    type: Literal["notice"] = "notice"
    code: Literal["backlog_skipped", "resync_required"]
    count: Annotated[int, Field(strict=True, ge=0)] = 0


ClientPacket = Annotated[Authenticate | Subscribe | Ping | Pong, Field(discriminator="type")]
ServerControl = Annotated[
    Authenticated | Snapshot | Notice | Ping | Pong, Field(discriminator="type")
]
CLIENT_PACKET = TypeAdapter(ClientPacket)
SERVER_CONTROL = TypeAdapter(ServerControl)
