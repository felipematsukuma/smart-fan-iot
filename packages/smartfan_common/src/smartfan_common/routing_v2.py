"""Credential-free v2 topic and queue topology; no broker side effects."""

from .contracts_v2 import (
    AlertV2,
    EventV2,
    QuarantinedV2,
    TelemetryPersistedV2,
    TelemetrySampleV2,
    parse_event_v2,
)
from .topology import QueueSpec

EVENTS = "smartfan.events"
JOBS = "smartfan.jobs"
DLX = "smartfan.dlx"
QUEUES_V2 = (
    QueueSpec("q.telemetry.writer", EVENTS, ("telemetry.*.hvac.*",), "writer", 32),
    QueueSpec("q.inference", EVENTS, ("persisted.*.hvac.*", "model.available"), "inference", 32),
    QueueSpec("q.control", EVENTS, ("telemetry.*.hvac.*", "insight.*", "ack.*"), "control", 16),
    QueueSpec(
        "q.events.api",
        EVENTS,
        ("frame.*", "alert.*", "ack.*", "device.*", "job.progress", "model.activated"),
        "api",
        32,
    ),
    QueueSpec("q.commands.gateway", EVENTS, ("command.*",), "gateway", 1),
    QueueSpec("q.jobs.generate", JOBS, ("job.generate",), "jobs-worker", 1),
    QueueSpec("q.jobs.train", JOBS, ("job.train",), "jobs-worker", 1),
    QueueSpec("q.dlq", DLX, ("#",), "administrator", 1),
)


def routing_key_v2(event: EventV2) -> tuple[str, str]:
    kind = event.tipo
    if isinstance(event, TelemetrySampleV2):
        return EVENTS, f"telemetry.{event.metadata.zone}.hvac.{event.dispositivo}"
    if isinstance(event, TelemetryPersistedV2):
        return EVENTS, f"persisted.{event.metadata.zone}.hvac.{event.dispositivo}"
    if kind == "transport.received":
        raise ValueError("Transport receipts have no AMQP route")
    if isinstance(event, QuarantinedV2):
        return DLX, f"failure.{event.conteudo.owner}"
    if kind in ("job.generate", "job.train"):
        return JOBS, kind
    if kind in ("job.progress", "model.available", "model.activated"):
        return EVENTS, kind
    if isinstance(event, AlertV2):
        return EVENTS, f"alert.{event.conteudo.severity}"
    prefix = {
        "frame.ready": "frame",
        "insight.predicted": "insight",
        "command.requested": "command",
        "command.applied": "ack",
        "command.rejected": "ack",
        "command.expired": "ack",
        "device.state": "device",
        "device.availability": "device",
    }[kind]
    return EVENTS, f"{prefix}.{event.dispositivo}"


def mqtt_topic_v2(event: EventV2) -> str:
    suffix = {
        "telemetry.sampled": "telemetry",
        "command.requested": "commands",
        "command.applied": "acks",
        "command.rejected": "acks",
        "command.expired": "acks",
        "device.state": "state",
        "device.availability": "availability",
        "transport.received": "receipts",
    }.get(event.tipo)
    if suffix is None or event.dispositivo is None:
        raise ValueError("Internal event has no MQTT device route")
    return f"devices/{event.dispositivo}/{suffix}"


def parse_mqtt_event_v2(topic: str, payload: str | bytes) -> EventV2:
    event = parse_event_v2(payload)
    if mqtt_topic_v2(event) != topic:
        raise ValueError("MQTT topic and event identity/type differ")
    return event
