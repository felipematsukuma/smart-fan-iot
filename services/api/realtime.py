"""Authorized durable snapshots; only fresh, ordered frames enter the live stream."""

from datetime import UTC, datetime

from smartfan_common.contracts_v2 import (
    AlertV2,
    CommandAckV2,
    DeviceAvailabilityV2,
    DeviceStateV2,
    EventV2,
    FrameReadyV2,
    JobProgressV2,
    ModelActivatedV2,
    parse_event_v2,
    payload_sha256,
)
from smartfan_common.provenance_v2 import telemetry_digest
from smartfan_common.reliability.amqp import authenticated_publisher
from smartfan_common.reliability.store import DurableStore
from smartfan_common.routing_v2 import routing_key_v2
from smartfan_common.ws_protocol import DeviceDescriptor, Snapshot, default_descriptor
from sqlalchemy import text

from .errors import Problem


def utc_now() -> datetime:
    return datetime.now(UTC)


def wire_time(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def fresh(event: EventV2, now: datetime) -> bool:
    age = (now - datetime.fromisoformat(event.timestamp)).total_seconds()
    if not 0 <= age <= 6:
        return False
    if isinstance(event, FrameReadyV2):
        observed = datetime.fromisoformat(event.metadata.observed_at)
        return (
            datetime.fromisoformat(event.timestamp) <= observed <= now
            and (now - observed).total_seconds() <= 6
        )
    return True


class EventStore:
    def __init__(self, store: DurableStore):
        if store.owner != "api":
            raise ValueError("API requires its own durable store")
        self.store = store

    def devices(self) -> dict[str, DeviceDescriptor]:
        with self.store.engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT device_id,zone,boot_id,last_sample_at FROM transport.device_status ORDER BY device_id LIMIT 1000"
                    )
                )
                .mappings()
                .all()
            )
        return {
            row["device_id"]: default_descriptor(
                row["device_id"],
                row["zone"],
                str(row["boot_id"]),
                wire_time(row["last_sample_at"]) if row["last_sample_at"] else None,
            )
            for row in rows
        }

    def authorize(
        self, requested: list[str] | tuple[str, ...] | None
    ) -> tuple[str, ...]:
        available = self.devices()
        selected = (
            tuple(dict.fromkeys(requested))
            if requested is not None
            else tuple(available)[:100]
        )
        if len(selected) > 100 or not set(selected) <= available.keys():
            raise Problem(403, "device_scope_forbidden", "Dispositivo não autorizado.")
        return selected

    def snapshot(self, selected: tuple[str, ...]) -> Snapshot:
        devices = self.devices()
        allowed = tuple(identity for identity in selected if identity in devices)
        with self.store.engine.connect() as conn:
            rows = (
                conn.execute(
                    text(
                        "SELECT payload FROM app.event_snapshots WHERE device_id=ANY(:ids) ORDER BY sampled_at"
                    ),
                    {"ids": list(allowed)},
                ).all()
                if allowed
                else []
            )
        now = utc_now()
        events = [parse_event_v2(bytes(row[0])) for row in rows]
        return Snapshot(
            server_time=wire_time(now),
            devices=[devices[identity] for identity in allowed],
            events=[
                event
                for event in events
                if (
                    fresh(event, now)
                    or (
                        isinstance(event, DeviceAvailabilityV2)
                        and datetime.fromisoformat(event.timestamp) <= now
                    )
                )
                and event.dispositivo in devices
                and (
                    not hasattr(event.metadata, "boot_id")
                    or event.metadata.boot_id == devices[event.dispositivo].boot_id
                )
            ],
        )

    def receive(
        self, payload: bytes, route: str, user_id: str | None, message_id: str | None
    ) -> tuple[EventV2 | None, bool]:
        try:
            event = parse_event_v2(payload)
            if (
                not isinstance(
                    event,
                    (
                        FrameReadyV2,
                        DeviceStateV2,
                        DeviceAvailabilityV2,
                        CommandAckV2,
                        JobProgressV2,
                        ModelActivatedV2,
                        AlertV2,
                    ),
                )
                or routing_key_v2(event)[1] != route
                or event.id != message_id
            ):
                raise ValueError("Invalid API event")
            origin = authenticated_publisher(event, user_id)
            with self.store.transaction() as conn:
                if (
                    not origin
                    and user_id is None
                    and event.metadata.producer == "simulator"
                ):
                    digest = conn.execute(
                        text(
                            "SELECT sha256 FROM transport.receipts WHERE event_id=:id"
                        ),
                        {"id": event.id},
                    ).scalar_one_or_none()
                    origin = digest == payload_sha256(payload)
                if not origin:
                    raise ValueError("Invalid authenticated producer")
                if isinstance(event, FrameReadyV2):
                    observed = conn.execute(
                        text(
                            "SELECT observed_at,sampled_at,device_id,boot_id,sequence,data_sha256,zone FROM transport.receipts WHERE event_id=:id"
                        ),
                        {"id": event.conteudo.source_event_id},
                    ).first()
                    if (
                        observed is None
                        or observed[0]
                        != datetime.fromisoformat(event.metadata.observed_at)
                        or observed[1] != datetime.fromisoformat(event.timestamp)
                        or observed[2] != event.dispositivo
                        or str(observed[3]) != event.metadata.boot_id
                        or observed[4] != event.metadata.sequence
                        or observed[5] != telemetry_digest(event.conteudo.telemetry)
                        or observed[6] != event.metadata.zone
                    ):
                        raise ValueError(
                            "Frame observation differs from gateway journal"
                        )
                result = self.store.receive(event.id, payload, route, connection=conn)
                if result != "accepted":
                    return None, False
                now = utc_now()
                recent = fresh(event, now)
                if event.dispositivo is not None:
                    device = conn.execute(
                        text(
                            "SELECT zone,boot_id FROM transport.device_status WHERE device_id=:id"
                        ),
                        {"id": event.dispositivo},
                    ).first()
                    if device is None or (
                        hasattr(event.metadata, "zone")
                        and event.metadata.zone != device[0]
                    ):
                        raise ValueError("Unregistered event device")
                    if hasattr(
                        event.metadata, "boot_id"
                    ) and event.metadata.boot_id != str(device[1]):
                        recent = False
                if recent and isinstance(
                    event, (FrameReadyV2, DeviceStateV2, DeviceAvailabilityV2)
                ):
                    metadata = event.metadata
                    changed = conn.execute(
                        text("""INSERT INTO app.event_snapshots(kind,device_id,event_id,source_event_id,boot_id,sequence,sampled_at,observed_at,payload)
                      VALUES(:kind,:device,:id,:source,:boot,:seq,:sample,:observed,:payload)
                      ON CONFLICT(kind,device_id) DO UPDATE SET event_id=excluded.event_id,source_event_id=excluded.source_event_id,
                      boot_id=excluded.boot_id,sequence=excluded.sequence,sampled_at=excluded.sampled_at,observed_at=excluded.observed_at,payload=excluded.payload,updated_at=clock_timestamp()
                      WHERE event_snapshots.sampled_at<excluded.sampled_at AND (excluded.kind='device.availability' OR event_snapshots.boot_id<>excluded.boot_id OR event_snapshots.sequence<excluded.sequence)
                      RETURNING event_id"""),
                        {
                            "kind": event.tipo,
                            "device": event.dispositivo,
                            "id": event.id,
                            "source": event.conteudo.source_event_id
                            if isinstance(event, FrameReadyV2)
                            else None,
                            "boot": metadata.boot_id,
                            "seq": metadata.sequence,
                            "sample": datetime.fromisoformat(event.timestamp),
                            "observed": datetime.fromisoformat(metadata.observed_at)
                            if hasattr(metadata, "observed_at")
                            else now,
                            "payload": payload,
                        },
                    ).scalar_one_or_none()
                    recent = changed is not None
                conn.execute(
                    text(
                        "UPDATE transport.inbox SET state='completed',finished_at=clock_timestamp() WHERE owner='api' AND event_id=:id"
                    ),
                    {"id": event.id},
                )
            return event, not recent
        except ValueError:
            self.store.quarantine(payload, route[:256], "invalid_api_event")
            return None, False
