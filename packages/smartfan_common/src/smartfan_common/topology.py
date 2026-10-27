"""Credential-free topology shared by future broker bootstrap and consumers."""

from dataclasses import dataclass

EVENTS_EXCHANGE = "smartfan.events"
JOBS_EXCHANGE = "smartfan.jobs"
DEAD_LETTER_EXCHANGE = "smartfan.dlx"


@dataclass(frozen=True)
class QueueSpec:
    name: str
    exchange: str
    bindings: tuple[str, ...]
    consumer: str
    prefetch: int


QUEUES = (
    QueueSpec("q.telemetry.writer", EVENTS_EXCHANGE, ("telemetry.raw.*.hvac.*",), "writer", 32),
    QueueSpec(
        "q.control",
        EVENTS_EXCHANGE,
        (
            "telemetry.raw.*.hvac.*",
            "insight.predicted.*.hvac.*",
            "command.applied.*.hvac.*",
            "command.rejected.*.hvac.*",
            "command.expired.*.hvac.*",
        ),
        "control",
        32,
    ),
    QueueSpec(
        "q.inference",
        EVENTS_EXCHANGE,
        ("telemetry.persisted.*.hvac.*", "model.activate.*"),
        "inference",
        32,
    ),
    QueueSpec("q.commands.gateway", EVENTS_EXCHANGE, ("command.requested.*.hvac.*",), "gateway", 1),
    QueueSpec(
        "q.events.api",
        EVENTS_EXCHANGE,
        (
            "telemetry.persisted.*.hvac.*",
            "insight.predicted.*.hvac.*",
            "command.*.*.hvac.*",
            "alert.*.*.hvac.*",
            "device.*.*.hvac.*",
            "job.progress",
            "model.activated",
        ),
        "api",
        32,
    ),
    QueueSpec("q.jobs.generate", JOBS_EXCHANGE, ("dataset.generate",), "jobs-worker", 1),
    QueueSpec("q.jobs.train", JOBS_EXCHANGE, ("model.train",), "jobs-worker", 1),
)

# Bootstrap attaches a DLX policy to each work queue; no automatic replay of commands.
DEAD_LETTER_QUEUE = "q.dlq"
DEAD_LETTER_BINDING = "#"
