"""Test-only inference stand-in: forwards an actual device sample, no prediction."""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import pika
from smartfan_common.contracts_v2 import (
    FrameReadyV2,
    TelemetrySampleV2,
    parse_event_v2,
    serialize_event_v2,
)
from smartfan_common.reliability.amqp import connect_amqp
from smartfan_common.reliability.database import engine_for
from sqlalchemy import text


def publish_latest_frame(after_sample: str | None = None) -> dict:
    engine = engine_for("gateway", Path("/run/secrets/postgres_gateway"))
    broker = None
    try:
        sample = None
        observed = None
        for _ in range(40):
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT payload,observed_at FROM transport.inbox WHERE owner='gateway' AND route='devices/ac_01/telemetry' AND payload IS NOT NULL ORDER BY observed_at DESC LIMIT 10"
                    )
                ).all()
            for row in rows:
                event = parse_event_v2(bytes(row[0]))
                if (
                    isinstance(event, TelemetrySampleV2)
                    and 0
                    <= (
                        datetime.now(UTC) - datetime.fromisoformat(event.timestamp)
                    ).total_seconds()
                    < 3
                    and (
                        after_sample is None
                        or datetime.fromisoformat(event.timestamp)
                        > datetime.fromisoformat(after_sample)
                    )
                ):
                    sample, observed = event, row[1]
                    break
            if sample:
                break
            time.sleep(0.25)
        if sample is None or observed is None:
            raise RuntimeError("No recent actual simulator sample")
        record = sample.model_dump()
        record.update(id=str(uuid4()), tipo="frame.ready")
        record["metadata"].update(
            producer="inference",
            observed_at=observed.isoformat().replace("+00:00", "Z"),
            causation_id=str(uuid5(NAMESPACE_URL, "smartfan:persisted:" + sample.id)),
        )
        telemetry = record["conteudo"]
        telemetry["source_event_id"] = sample.id
        record["conteudo"] = {
            "source_event_id": sample.id,
            "telemetry": telemetry,
            "insight": {
                "status": "model_unavailable",
                "model_version": None,
                "feature_version": "hvac-window-v1",
                "health_score": None,
                "rul_calendar_hours": None,
            },
        }
        frame = FrameReadyV2.model_validate(record)
        broker = connect_amqp("inference", Path("/run/secrets/rabbit_inference"))
        channel = broker.channel()
        channel.confirm_delivery()
        channel.basic_publish(
            "smartfan.events",
            "frame.ac_01",
            serialize_event_v2(frame),
            mandatory=True,
            properties=pika.BasicProperties(
                user_id="inference",
                message_id=frame.id,
                delivery_mode=2,
                content_type="application/json",
            ),
        )
        return {
            "id": frame.id,
            "sampled_at": frame.timestamp,
            "power_w": frame.conteudo.telemetry.readings.power_w,
        }
    finally:
        if broker is not None and broker.is_open:
            broker.close()
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--after-sample")
    args = parser.parse_args()
    print(json.dumps(publish_latest_frame(args.after_sample)))
