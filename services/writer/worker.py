"""Influx write precedes persisted/outbox; PostgreSQL reserves every point key."""

from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from smartfan_common.contracts_v2 import (
    TelemetryPersistedV2,
    TelemetrySampleV2,
    parse_event_v2,
    payload_sha256,
    serialize_event_v2,
)
from smartfan_common.influx_v2 import InfluxHTTP, telemetry_point
from smartfan_common.reliability.store import Delivery, DurableStore, Outbound
from smartfan_common.routing_v2 import routing_key_v2
from sqlalchemy import text


class PointCollision(ValueError):
    pass


class Writer:
    def __init__(self, store: DurableStore, influx: InfluxHTTP):
        if store.owner != "writer":
            raise ValueError("Writer requires its own database account")
        self.store, self.influx = store, influx

    def provenance(self, event_id: str, payload: bytes) -> datetime:
        with self.store.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT observed_at,sha256 FROM transport.receipts WHERE event_id=:id"
                ),
                {"id": event_id},
            ).first()
        if row is None or row[1] != payload_sha256(payload):
            raise ValueError("No matching durable gateway receipt")
        return row[0]

    def receive(
        self, payload: bytes, route: str, user_id: str | None, message_id: str | None
    ) -> bool:
        try:
            event = parse_event_v2(payload)
            if (
                not isinstance(event, TelemetrySampleV2)
                or user_id not in ("gateway", None)
                or message_id != event.id
                or routing_key_v2(event)[1] != route
            ):
                raise ValueError("Invalid telemetry origin")
            self.provenance(event.id, payload)
        except ValueError:
            self.store.quarantine(payload, route[:256], "invalid_telemetry_origin")
            return False
        return self.store.receive(event.id, payload, route) != "conflict"

    def process(self, delivery: Delivery) -> None:
        event = parse_event_v2(delivery.payload)
        if not isinstance(event, TelemetrySampleV2):
            raise TypeError("Invalid writer event kind")
        observed = self.provenance(event.id, delivery.payload)
        key, line = telemetry_point(event, observed)
        parameters = {
            "key": key,
            "id": event.id,
            "sha": payload_sha256(delivery.payload),
            "line": payload_sha256(line),
        }
        with self.store.transaction() as conn:
            conn.execute(
                text(
                    "INSERT INTO transport.influx_points(point_key,event_id,source_sha256,line_sha256) VALUES(:key,:id,:sha,:line) ON CONFLICT DO NOTHING"
                ),
                parameters,
            )
            row = conn.execute(
                text(
                    "SELECT event_id,source_sha256,line_sha256 FROM transport.influx_points WHERE point_key=:key"
                ),
                parameters,
            ).first()
            if (
                row is None
                or str(row[0]) != event.id
                or row[1] != parameters["sha"]
                or row[2] != parameters["line"]
            ):
                raise PointCollision("Another source already reserved this point")
        self.influx.write(line)
        data = event.model_dump()
        data.update(
            id=str(uuid5(NAMESPACE_URL, "smartfan:persisted:" + event.id)),
            tipo="telemetry.persisted",
        )
        data["metadata"].update(
            producer="writer",
            causation_id=event.id,
            observed_at=observed.isoformat().replace("+00:00", "Z"),
        )
        data["conteudo"]["source_event_id"] = event.id
        persisted = TelemetryPersistedV2.model_validate(data)
        exchange, route = routing_key_v2(persisted)
        self.store.finish(
            delivery,
            outgoing=(
                Outbound(persisted.id, serialize_event_v2(persisted), exchange, route),
            ),
        )
