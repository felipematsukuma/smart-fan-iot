"""Closed, versioned JSON wire schemas. No live event accepts training labels.

UTC strings deliberately have the same validation in Python and JSON Schema.
Clock-dependent freshness/expiry are separate from structural validation.
"""

from datetime import datetime, timezone
from typing import Annotated, Literal, cast, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    field_validator,
    model_validator,
)

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,64}$", strict=True)]
UUIDString = Annotated[
    str,
    Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        strict=True,
        json_schema_extra={"format": "uuid"},
    ),
]
UTCString = Annotated[
    str,
    Field(
        pattern=(
            r"^[1-9]\d{3}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
            r"T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?Z$"
        ),
        strict=True,
        json_schema_extra={"format": "date-time"},
    ),
]
Unsigned = Annotated[int, Field(strict=True, ge=0, le=9007199254740991)]
NonNegative = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
Fraction = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
FeatureVersion = Literal["hvac-window-v1"]
SensorName = Literal[
    "current_a", "compressor_case_temp_c", "vibration_rms_mm_s", "indoor_temp_c", "outdoor_temp_c"
]


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Metadata(WireModel):
    producer: Literal[
        "simulator", "gateway", "writer", "api", "control", "inference", "jobs-worker"
    ]
    correlation_id: UUIDString | None = None
    causation_id: UUIDString | None = None


class DeviceMetadata(Metadata):
    boot_id: UUIDString
    sequence: Unsigned


class Envelope(WireModel):
    schema_version: Literal["1.0"]
    id: UUIDString
    timestamp: UTCString
    type: str
    stream: str
    device_id: Identifier | None
    zone: Identifier | None
    equipment_type: Literal["ac_split_onoff"] | None
    metadata: Metadata

    @field_validator("timestamp")
    @classmethod
    def real_calendar_date(cls, value: str) -> str:
        datetime.fromisoformat(value)
        return value


class DeviceEnvelope(Envelope):
    stream: Literal["live"]
    device_id: Identifier
    zone: Identifier
    equipment_type: Literal["ac_split_onoff"]


class Readings(WireModel):
    current_a: Annotated[float, Field(strict=True, ge=0, le=200, allow_inf_nan=False)] | None
    compressor_case_temp_c: (
        Annotated[float, Field(strict=True, ge=-50, le=200, allow_inf_nan=False)] | None
    )
    vibration_rms_mm_s: (
        Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)] | None
    )
    indoor_temp_c: Annotated[float, Field(strict=True, ge=-50, le=80, allow_inf_nan=False)] | None
    outdoor_temp_c: Annotated[float, Field(strict=True, ge=-50, le=80, allow_inf_nan=False)] | None
    power_w: Annotated[float, Field(strict=True, ge=0, le=100000, allow_inf_nan=False)] | None


class Actuators(WireModel):
    compressor_on: Annotated[bool, Field(strict=True)]
    condenser_fan_on: Annotated[bool, Field(strict=True)]


class Quality(WireModel):
    missing_fields: list[SensorName] = Field(max_length=5, json_schema_extra={"uniqueItems": True})

    @field_validator("missing_fields")
    @classmethod
    def unique_fields(cls, value: list[SensorName]) -> list[SensorName]:
        if len(value) != len(set(value)):
            raise ValueError("Missing fields must be unique")
        return value


def _quality_conditions() -> list[JsonValue]:
    """Express missing/null consistency in portable JSON Schema as well as Python."""
    conditions: list[dict[str, object]] = []
    for name in get_args(SensorName):
        contains = {"contains": {"const": name}}
        conditions.append(
            {
                "if": {
                    "type": "object",
                    "properties": {
                        "readings": {"type": "object", "properties": {name: {"type": "null"}}}
                    },
                },
                "then": {
                    "type": "object",
                    "properties": {
                        "quality": {
                            "type": "object",
                            "properties": {"missing_fields": {"type": "array", **contains}},
                        }
                    },
                },
                "else": {
                    "type": "object",
                    "properties": {
                        "quality": {
                            "type": "object",
                            "properties": {"missing_fields": {"type": "array", "not": contains}},
                        }
                    },
                },
            }
        )
    # This schema builder constructs JSON literals only; nested dicts are invariant in mypy.
    return cast(list[JsonValue], conditions)


class TelemetryData(WireModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_extra={"allOf": _quality_conditions()}
    )
    readings: Readings
    actuators: Actuators
    quality: Quality

    @model_validator(mode="after")
    def missing_matches_readings(self) -> "TelemetryData":
        expected = {name for name in get_args(SensorName) if getattr(self.readings, name) is None}
        if expected != set(self.quality.missing_fields):
            raise ValueError("Missing-field markers must match null sensor readings")
        return self


class TelemetryEvent(DeviceEnvelope):
    type: Literal["telemetry.sampled", "telemetry.persisted"]
    metadata: DeviceMetadata
    data: TelemetryData


class StateData(WireModel):
    actuators: Actuators
    mode: Literal["manual", "auto"]


class StateEvent(DeviceEnvelope):
    type: Literal["device.state"]
    metadata: DeviceMetadata
    data: StateData


class AvailabilityData(WireModel):
    status: Literal["online", "offline"]


class AvailabilityEvent(DeviceEnvelope):
    type: Literal["device.availability"]
    metadata: DeviceMetadata
    data: AvailabilityData


class CommandData(WireModel):
    target_boot_id: UUIDString
    revision: Unsigned
    desired: Actuators
    mode: Literal["manual", "auto"]
    expires_at: UTCString

    @field_validator("expires_at")
    @classmethod
    def real_calendar_date(cls, value: str) -> str:
        datetime.fromisoformat(value)
        return value


class CommandEvent(DeviceEnvelope):
    type: Literal["command.requested"]
    data: CommandData


class AckData(WireModel):
    command_id: UUIDString
    revision: Unsigned
    status: Literal["applied"]
    observed: Actuators
    reason: Literal["ok"]


class RejectedAckData(WireModel):
    command_id: UUIDString
    revision: Unsigned
    status: Literal["rejected"]
    observed: Actuators
    reason: Literal["interlock", "short_cycle", "obsolete_revision", "wrong_boot"]


class ExpiredAckData(WireModel):
    command_id: UUIDString
    revision: Unsigned
    status: Literal["expired"]
    observed: Actuators
    reason: Literal["expired"]


class AckEvent(DeviceEnvelope):
    type: Literal["command.applied"]
    data: AckData


class RejectedAckEvent(DeviceEnvelope):
    type: Literal["command.rejected"]
    data: RejectedAckData


class ExpiredAckEvent(DeviceEnvelope):
    type: Literal["command.expired"]
    data: ExpiredAckData


class InsightData(WireModel):
    source_event_id: UUIDString
    model_version: Identifier
    feature_version: FeatureVersion
    status: Literal["valid"]
    rul_operating_hours: NonNegative
    health_score: Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)] | None


class UnavailableInsightData(WireModel):
    source_event_id: UUIDString
    model_version: Identifier
    feature_version: FeatureVersion
    status: Literal["warming_up", "insufficient_data", "out_of_domain", "inactive"]
    rul_operating_hours: None
    health_score: Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)] | None


class InsightEvent(DeviceEnvelope):
    type: Literal["insight.predicted"]
    data: Annotated[InsightData | UnavailableInsightData, Field(discriminator="status")]


class AlertData(WireModel):
    alert_id: UUIDString
    rule_id: UUIDString
    severity: Literal["info", "warning", "critical"]
    reason_code: Identifier


class AlertEvent(DeviceEnvelope):
    type: Literal["alert.raised", "alert.cleared", "alert.acknowledged"]
    data: AlertData


class SystemEnvelope(Envelope):
    stream: Literal["system"]
    device_id: None
    zone: None
    equipment_type: None


class GenerateData(WireModel):
    job_id: UUIDString
    dataset_id: UUIDString
    seed: Unsigned
    records: Annotated[int, Field(strict=True, ge=1, le=10000000)]
    equipment_count: Annotated[int, Field(strict=True, ge=3, le=1000)]
    chunk_size: Annotated[int, Field(strict=True, ge=128, le=100000)]
    scenarios: list[Literal["healthy", "mechanical_wear", "heat_transfer_loss"]] = Field(
        min_length=1, max_length=3, json_schema_extra={"uniqueItems": True}
    )
    noise_std: NonNegative
    missing_fraction: Fraction
    outlier_fraction: Fraction

    @field_validator("scenarios")
    @classmethod
    def unique_scenarios(
        cls, value: list[Literal["healthy", "mechanical_wear", "heat_transfer_loss"]]
    ) -> list[Literal["healthy", "mechanical_wear", "heat_transfer_loss"]]:
        if len(value) != len(set(value)):
            raise ValueError("Scenarios must be unique")
        return value


class GenerateEvent(SystemEnvelope):
    type: Literal["dataset.generate.requested"]
    data: GenerateData


class TrainData(WireModel):
    job_id: UUIDString
    dataset_id: UUIDString
    seed: Unsigned
    feature_version: FeatureVersion
    algorithms: list[Literal["ridge", "hist_gradient_boosting"]] = Field(
        min_length=1, max_length=2, json_schema_extra={"uniqueItems": True}
    )

    @field_validator("algorithms")
    @classmethod
    def unique_algorithms(
        cls, value: list[Literal["ridge", "hist_gradient_boosting"]]
    ) -> list[Literal["ridge", "hist_gradient_boosting"]]:
        if len(value) != len(set(value)):
            raise ValueError("Algorithms must be unique")
        return value


class TrainEvent(SystemEnvelope):
    type: Literal["model.train.requested"]
    data: TrainData


class ProgressData(WireModel):
    job_id: UUIDString
    kind: Literal["dataset.generate", "model.train"]
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    processed: Unsigned
    total: Unsigned


class ProgressEvent(SystemEnvelope):
    type: Literal["job.progress"]
    data: ProgressData


class ModelData(WireModel):
    model_version: Identifier
    feature_version: FeatureVersion
    sha256: Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]


class ModelEvent(SystemEnvelope):
    type: Literal["model.activation.requested", "model.activated"]
    data: ModelData


EventV1 = Annotated[
    TelemetryEvent
    | StateEvent
    | AvailabilityEvent
    | CommandEvent
    | AckEvent
    | RejectedAckEvent
    | ExpiredAckEvent
    | InsightEvent
    | AlertEvent
    | GenerateEvent
    | TrainEvent
    | ProgressEvent
    | ModelEvent,
    Field(discriminator="type"),
]
EVENT_ADAPTER: TypeAdapter[EventV1] = TypeAdapter(EventV1)


def parse_event(payload: str | bytes) -> EventV1:
    """Validate JSON only; routing, expiry and authorization are independent checks."""
    return EVENT_ADAPTER.validate_json(payload)


def command_expired(event: CommandEvent, now: datetime) -> bool:
    """Reject impossible lifetimes and expired commands, using an injected UTC clock."""
    if now.tzinfo is None:
        raise ValueError("An aware clock is required")
    expiry = datetime.fromisoformat(event.data.expires_at)
    return expiry <= datetime.fromisoformat(event.timestamp) or expiry <= now


def event_fresh(event: DeviceEnvelope, now: datetime, max_age_seconds: float = 5) -> bool:
    if now.tzinfo is None or max_age_seconds <= 0:
        raise ValueError("An aware clock and positive freshness limit are required")
    age = (now.astimezone(timezone.utc) - datetime.fromisoformat(event.timestamp)).total_seconds()
    return 0 <= age <= max_age_seconds


def routing_key(event: EventV1) -> tuple[str, str]:
    """Return the sole allowed exchange/key for each supported event type."""
    if isinstance(event, GenerateEvent):
        return "smartfan.jobs", "dataset.generate"
    if isinstance(event, TrainEvent):
        return "smartfan.jobs", "model.train"
    if isinstance(event, ModelEvent) and event.type == "model.activation.requested":
        return "smartfan.events", f"model.activate.{event.data.model_version}"
    if isinstance(event, SystemEnvelope):
        return "smartfan.events", event.type
    prefix = "telemetry.raw" if event.type == "telemetry.sampled" else event.type
    return "smartfan.events", f"{prefix}.{event.zone}.hvac.{event.device_id}"


def mqtt_topic(event: EventV1) -> str:
    """No lab/system/derived event may loop back to a device MQTT topic."""
    if isinstance(event, TelemetryEvent) and event.type == "telemetry.sampled":
        suffix = "telemetry"
    elif isinstance(event, CommandEvent):
        suffix = "commands"
    elif isinstance(event, (AckEvent, RejectedAckEvent, ExpiredAckEvent)):
        suffix = "acks"
    elif isinstance(event, StateEvent):
        suffix = "state"
    elif isinstance(event, AvailabilityEvent):
        suffix = "availability"
    else:
        raise ValueError("This event has no device MQTT route")
    return f"devices/{event.device_id}/{suffix}"


def parse_mqtt_event(topic: str, payload: str | bytes) -> EventV1:
    event = parse_event(payload)
    if topic != mqtt_topic(event):
        raise ValueError("MQTT topic and event identity/type differ")
    return event
