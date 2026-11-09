"""Closed AIoT v2 wire contracts. V1 remains independent and unchanged.

Structural validation is shared as JSON Schema. Cross-field invariants are
also checked by the frontend validator; transport authorization is separate.
"""

import hashlib
import json
import math
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BeforeValidator, Field, TypeAdapter, model_validator

from .contracts import (
    Actuators,
    FeatureVersion,
    Identifier,
    NonNegative,
    TelemetryData,
    UTCString,
    UUIDString,
    WireModel,
)
from .contracts import (
    Unsigned as V1Unsigned,
)


def _calendar(value: str) -> str:
    datetime.fromisoformat(value)
    return value


UTC = Annotated[UTCString, AfterValidator(_calendar)]


def _wire_integer(value: object) -> object:
    # JSON/JSON Schema integers are mathematical values: 120.0 and 1.2e2
    # have the same meaning as 120. Never coerce strings or booleans.
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    return value


Unsigned = Annotated[V1Unsigned, BeforeValidator(_wire_integer)]
Digest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
MAX_EVENT_BYTES = 16 * 1024
MAX_QUARANTINE_BYTES = 32 * 1024


def _clock_scale(value: object) -> object:
    if isinstance(value, bool):
        raise ValueError("Clock scale must be numeric one, not a boolean")
    return value


class MetadataV2(WireModel):
    producer: Literal[
        "simulator", "gateway", "writer", "control", "inference", "api", "jobs-worker"
    ]
    causation_id: UUIDString | None


class DeviceMetadataV2(MetadataV2):
    boot_id: UUIDString
    sequence: Unsigned
    zone: Identifier
    equipment_type: Literal["ac_split_onoff"]
    clock_scale: Annotated[Literal[1], BeforeValidator(_clock_scale)]


class SimulatorMetadata(DeviceMetadataV2):
    producer: Literal["simulator"]


class WriterMetadata(DeviceMetadataV2):
    producer: Literal["writer"]
    observed_at: UTC


class InferenceMetadata(DeviceMetadataV2):
    producer: Literal["inference"]
    observed_at: UTC


class GatewayMetadata(DeviceMetadataV2):
    producer: Literal["gateway"]
    observed_at: UTC


class ControlMetadata(DeviceMetadataV2):
    producer: Literal["control"]
    observed_at: UTC


class CommandMetadata(MetadataV2):
    producer: Literal["api", "control"]
    zone: Identifier
    equipment_type: Literal["ac_split_onoff"]


class ApiMetadata(MetadataV2):
    producer: Literal["api"]


class WorkerMetadata(MetadataV2):
    producer: Literal["jobs-worker"]


class ModelMetadata(MetadataV2):
    producer: Literal["inference"]


class EnvelopeV2(WireModel):
    id: UUIDString
    schema_version: Literal["2.0", "2.1"]
    timestamp: UTC
    correlation_id: UUIDString | None


class TelemetrySampleV2(EnvelopeV2):
    tipo: Literal["telemetry.sampled"]
    dispositivo: Identifier
    metadata: SimulatorMetadata
    conteudo: TelemetryData


class PersistedData(TelemetryData):
    source_event_id: UUIDString


class TelemetryPersistedV2(EnvelopeV2):
    tipo: Literal["telemetry.persisted"]
    dispositivo: Identifier
    metadata: WriterMetadata
    conteudo: PersistedData


class ValidInsightV2(WireModel):
    status: Literal["valid"]
    model_version: Identifier
    feature_version: FeatureVersion
    health_score: Annotated[float, Field(strict=True, ge=0, le=100, allow_inf_nan=False)]
    rul_calendar_hours: NonNegative


class UnavailableInsightV2(WireModel):
    status: Literal[
        "warming_up", "insufficient_data", "inactive", "stale", "model_unavailable", "out_of_domain"
    ]
    model_version: Identifier | None
    feature_version: FeatureVersion
    health_score: None
    rul_calendar_hours: None


InsightV2 = Annotated[ValidInsightV2 | UnavailableInsightV2, Field(discriminator="status")]


class FrameData(WireModel):
    source_event_id: UUIDString
    telemetry: PersistedData
    insight: InsightV2

    @model_validator(mode="after")
    def source_matches(self) -> "FrameData":
        if self.source_event_id != self.telemetry.source_event_id:
            raise ValueError("Frame and telemetry source identities differ")
        return self


class FrameReadyV2(EnvelopeV2):
    tipo: Literal["frame.ready"]
    dispositivo: Identifier
    metadata: InferenceMetadata
    conteudo: FrameData


class ValidSourceInsight(ValidInsightV2):
    source_event_id: UUIDString


class UnavailableSourceInsight(UnavailableInsightV2):
    source_event_id: UUIDString


class InsightPredictedV2(EnvelopeV2):
    tipo: Literal["insight.predicted"]
    dispositivo: Identifier
    metadata: InferenceMetadata
    conteudo: Annotated[
        ValidSourceInsight | UnavailableSourceInsight, Field(discriminator="status")
    ]


class DesiredActuators(Actuators):
    model_config = {
        "extra": "forbid",
        "frozen": True,
        "json_schema_extra": {
            "not": {
                "properties": {
                    "compressor_on": {"const": True},
                    "condenser_fan_on": {"const": False},
                },
                "required": ["compressor_on", "condenser_fan_on"],
            }
        },
    }

    @model_validator(mode="after")
    def interlock(self) -> "DesiredActuators":
        if self.compressor_on and not self.condenser_fan_on:
            raise ValueError("Compressor requires condenser fan")
        return self


class CommandDataV2(WireModel):
    command_id: UUIDString
    target_boot_id: UUIDString
    revision: Unsigned
    desired: DesiredActuators
    mode: Literal["manual", "auto"]
    expires_at: UTC
    reason_code: Identifier


class CommandRequestedV2(EnvelopeV2):
    tipo: Literal["command.requested"]
    dispositivo: Identifier
    metadata: CommandMetadata
    conteudo: CommandDataV2

    @model_validator(mode="after")
    def command_identity_and_lifetime(self) -> "CommandRequestedV2":
        if self.id != self.conteudo.command_id:
            raise ValueError("Command identity must equal envelope identity")
        if datetime.fromisoformat(self.conteudo.expires_at) <= datetime.fromisoformat(
            self.timestamp
        ):
            raise ValueError("Command expiration must follow creation")
        return self


class AckDataV2(WireModel):
    command_id: UUIDString
    revision: Unsigned
    observed: Actuators
    reason_code: Identifier


class CommandAckV2(EnvelopeV2):
    tipo: Literal["command.applied", "command.rejected", "command.expired"]
    dispositivo: Identifier
    metadata: SimulatorMetadata
    conteudo: AckDataV2


class StateDataV2(WireModel):
    actuators: Actuators
    mode: Literal["manual", "auto"]
    manual_cooling_block: Annotated[bool, Field(strict=True)]
    reason_code: Identifier
    last_revision: Unsigned | None = None


class DeviceStateV2(EnvelopeV2):
    model_config = {
        "extra": "forbid",
        "frozen": True,
        "json_schema_extra": {
            "allOf": [
                {
                    "if": {"type": "object", "properties": {"schema_version": {"const": "2.1"}}},
                    "then": {
                        "type": "object",
                        "properties": {
                            "conteudo": {
                                "type": "object",
                                "required": ["last_revision"],
                                "properties": {"last_revision": {"type": "integer"}},
                            }
                        },
                    },
                }
            ]
        },
    }
    tipo: Literal["device.state"]
    dispositivo: Identifier
    metadata: SimulatorMetadata
    conteudo: StateDataV2

    @model_validator(mode="after")
    def revision_required_in_v21(self) -> "DeviceStateV2":
        if self.schema_version == "2.1" and self.conteudo.last_revision is None:
            raise ValueError("State v2.1 requires observed command revision")
        return self


class AvailabilityDataV2(WireModel):
    status: Literal["online", "offline"]
    reason_code: Identifier


class DeviceAvailabilityV2(EnvelopeV2):
    tipo: Literal["device.availability"]
    dispositivo: Identifier
    metadata: SimulatorMetadata | GatewayMetadata
    conteudo: AvailabilityDataV2


class ReceiptDataV2(WireModel):
    source_event_id: UUIDString
    status: Literal["durably_received"]


class TransportReceiptV2(EnvelopeV2):
    tipo: Literal["transport.received"]
    dispositivo: Identifier
    metadata: GatewayMetadata
    conteudo: ReceiptDataV2


class AlertDataV2(WireModel):
    alert_id: UUIDString
    rule_id: UUIDString
    severity: Literal["info", "warning", "critical"]
    source_event_id: UUIDString
    reason_code: Identifier


class AlertV2(EnvelopeV2):
    tipo: Literal["alert.raised", "alert.cleared"]
    dispositivo: Identifier
    metadata: ControlMetadata
    conteudo: AlertDataV2


class JobRequestData(WireModel):
    job_id: UUIDString
    dataset_id: UUIDString
    config_version: Annotated[
        int, Field(strict=True, ge=1, le=9007199254740991), BeforeValidator(_wire_integer)
    ]


class JobRequestedV2(EnvelopeV2):
    tipo: Literal["job.generate", "job.train"]
    dispositivo: None
    metadata: ApiMetadata
    conteudo: JobRequestData


class ProgressDataV2(WireModel):
    job_id: UUIDString
    kind: Literal["generate", "train"]
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    processed: Unsigned
    total: Unsigned
    reason_code: Identifier | None = None

    @model_validator(mode="after")
    def bounded_progress(self) -> "ProgressDataV2":
        if self.processed > self.total:
            raise ValueError("Processed exceeds total")
        return self


class JobProgressV2(EnvelopeV2):
    tipo: Literal["job.progress"]
    dispositivo: None
    metadata: WorkerMetadata
    conteudo: ProgressDataV2


class ModelDataV2(WireModel):
    model_version: Identifier
    feature_version: FeatureVersion
    dataset_id: UUIDString
    sha256: Digest


class ModelAvailableV2(EnvelopeV2):
    tipo: Literal["model.available"]
    dispositivo: None
    metadata: WorkerMetadata
    conteudo: ModelDataV2


class ModelActivatedV2(EnvelopeV2):
    tipo: Literal["model.activated"]
    dispositivo: None
    metadata: ModelMetadata
    conteudo: ModelDataV2


class QuarantineBase(WireModel):
    failure_id: UUIDString
    owner: Identifier
    reason_code: Identifier
    original_sha256: Digest
    original_route: Annotated[str, Field(strict=True, min_length=1, max_length=256)]
    attempts: Unsigned


class InlineQuarantine(QuarantineBase):
    original_bytes_b64: Annotated[
        str,
        Field(
            strict=True,
            max_length=21848,
            pattern=r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$",
        ),
    ]
    original_ref: None


class ReferencedQuarantine(QuarantineBase):
    original_bytes_b64: None
    original_ref: UUIDString


class QuarantinedV2(EnvelopeV2):
    tipo: Literal["message.quarantined"]
    dispositivo: Identifier | None
    metadata: MetadataV2
    conteudo: InlineQuarantine | ReferencedQuarantine


EventV2 = Annotated[
    TelemetrySampleV2
    | TelemetryPersistedV2
    | FrameReadyV2
    | InsightPredictedV2
    | CommandRequestedV2
    | CommandAckV2
    | DeviceStateV2
    | DeviceAvailabilityV2
    | TransportReceiptV2
    | AlertV2
    | JobRequestedV2
    | JobProgressV2
    | ModelAvailableV2
    | ModelActivatedV2
    | QuarantinedV2,
    Field(discriminator="tipo"),
]
EVENT_V2_ADAPTER: TypeAdapter[EventV2] = TypeAdapter(EventV2)


def parse_event_v2(payload: bytes | str) -> EventV2:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if len(raw) > MAX_QUARANTINE_BYTES:
        raise ValueError("Event exceeds transport limit")
    event = EVENT_V2_ADAPTER.validate_json(raw)
    if event.tipo != "message.quarantined" and len(raw) > MAX_EVENT_BYTES:
        raise ValueError("Event exceeds normal transport limit")
    return event


def serialize_event_v2(event: EventV2) -> bytes:
    """Serialize once; callers persist/retry these exact bytes, never re-enrich them."""
    raw = json.dumps(
        event.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    parse_event_v2(raw)
    return raw


def payload_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def command_expired_v2(event: CommandRequestedV2, now: datetime) -> bool:
    if now.tzinfo is None:
        raise ValueError("Clock must be timezone aware")
    return now >= datetime.fromisoformat(event.conteudo.expires_at)


def event_fresh_v2(event: EventV2, now: datetime, max_age_seconds: float = 6) -> bool:
    if now.tzinfo is None or not math.isfinite(max_age_seconds) or max_age_seconds <= 0:
        raise ValueError("An aware clock and positive age limit are required")
    if event.dispositivo is None:
        return False
    age = (now.astimezone(timezone.utc) - datetime.fromisoformat(event.timestamp)).total_seconds()
    return 0 <= age <= max_age_seconds
