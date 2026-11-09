"""Durable protocol boundary; network adapters never acknowledge before commit."""

from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from smartfan_common.contracts_v2 import (
    CommandAckV2,
    CommandRequestedV2,
    DeviceAvailabilityV2,
    DeviceStateV2,
    TelemetrySampleV2,
    TransportReceiptV2,
    parse_event_v2,
    payload_sha256,
    serialize_event_v2,
)
from smartfan_common.reliability.amqp import authenticated_publisher
from smartfan_common.reliability.origins import record_origin
from smartfan_common.reliability.store import DurableStore, Outbound
from smartfan_common.routing_v2 import (
    mqtt_topic_v2,
    parse_mqtt_event_v2,
    routing_key_v2,
)
from sqlalchemy import text


class GatewayBridge:
    def __init__(self, store: DurableStore, devices: dict[str, str] | None = None):
        if store.owner != "gateway":
            raise ValueError("Gateway requires its own durable store")
        self.store = store
        self.devices = dict(devices) if devices is not None else None

    def registered(self, identity: str, zone: str, *, active: bool = False) -> bool:
        if self.devices is not None:
            return self.devices.get(identity) == zone
        with self.store.engine.connect() as conn:
            row = conn.execute(
                text("SELECT zone,enabled FROM app.device_registry WHERE id=:id"),
                {"id": identity},
            ).first()
        return bool(row and row[0] == zone and (row[1] or not active))

    def receive_device(self, topic: str, payload: bytes) -> tuple[str, bytes] | None:
        try:
            return self._receive_device(topic, payload)
        except ValueError:
            # A semantic ACK failure rolls back receive/outbox/presence together.
            self.store.quarantine(payload, topic[:256], "invalid_device_ack")
            return None

    def _receive_device(self, topic: str, payload: bytes) -> tuple[str, bytes] | None:
        try:
            event = parse_mqtt_event_v2(topic, payload)
            if (
                event.metadata.producer != "simulator"
                or event.tipo
                not in (
                    "telemetry.sampled",
                    "device.state",
                    "device.availability",
                    "command.applied",
                    "command.rejected",
                    "command.expired",
                )
                or not self.registered(event.dispositivo or "", event.metadata.zone)
            ):
                raise ValueError("Device identity is not registered")
        except ValueError:
            self.store.quarantine(payload, topic[:256], "invalid_device_event")
            return None
        exchange, route = routing_key_v2(event)
        with self.store.transaction() as conn:
            result = self.store.receive(
                event.id,
                payload,
                topic,
                outgoing=()
                if isinstance(event, DeviceAvailabilityV2)
                else (Outbound(event.id, payload, exchange, route),),
                connection=conn,
            )
            if result == "conflict":
                return None
            observed = self.store.received_at(event.id, connection=conn)
            assert observed is not None
            if isinstance(event, TelemetrySampleV2):
                record_origin(conn, event)
            if result == "accepted":
                if isinstance(event, DeviceAvailabilityV2):
                    report = event.model_dump()
                    report.update(
                        id=str(
                            uuid5(NAMESPACE_URL, "smartfan:availability:" + event.id)
                        ),
                        timestamp=observed.isoformat().replace("+00:00", "Z"),
                    )
                    report["metadata"].update(
                        producer="gateway",
                        causation_id=event.id,
                        observed_at=observed.isoformat().replace("+00:00", "Z"),
                    )
                    forwarded = DeviceAvailabilityV2.model_validate(report)
                    self.store.enqueue(
                        Outbound(
                            forwarded.id, serialize_event_v2(forwarded), exchange, route
                        ),
                        connection=conn,
                    )
                self._presence(conn, event)
                if isinstance(event, CommandAckV2):
                    previous = conn.execute(
                        text(
                            "SELECT ack_sha256 FROM transport.command_results WHERE command_id=:id"
                        ),
                        {"id": event.conteudo.command_id},
                    ).scalar_one_or_none()
                    if previous is not None and previous != payload_sha256(payload):
                        raise ValueError("Conflicting physical acknowledgement")
                    original = conn.execute(
                        text(
                            "SELECT payload FROM transport.inbox WHERE owner='gateway' AND event_id=:id"
                        ),
                        {"id": event.conteudo.command_id},
                    ).scalar_one_or_none()
                    if original is not None:
                        command = parse_event_v2(bytes(original))
                        if (
                            not isinstance(command, CommandRequestedV2)
                            or command.dispositivo != event.dispositivo
                            or command.conteudo.revision != event.conteudo.revision
                            or (
                                event.tipo == "command.applied"
                                and command.conteudo.target_boot_id
                                != event.metadata.boot_id
                            )
                            or (
                                event.tipo == "command.applied"
                                and command.conteudo.desired.model_dump()
                                != event.conteudo.observed.model_dump()
                            )
                        ):
                            # Rolling back also rolls back the outgoing ACK and receipt.
                            raise ValueError(
                                "Acknowledgement does not match durable command"
                            )
                        conn.execute(
                            text(
                                "INSERT INTO transport.command_results(command_id,ack_event_id,ack_sha256,result) VALUES(:id,:ack,:sha,:result) ON CONFLICT(command_id) DO NOTHING"
                            ),
                            {
                                "id": command.id,
                                "ack": event.id,
                                "sha": payload_sha256(payload),
                                "result": event.tipo,
                            },
                        )
                # Device processing is already complete in this transaction;
                # only the independent confirmed AMQP outbox remains pending.
                conn.execute(
                    text(
                        "UPDATE transport.inbox SET state='completed',finished_at=clock_timestamp() WHERE owner='gateway' AND event_id=:id"
                    ),
                    {"id": event.id},
                )
        # Returning from the context above means PostgreSQL committed successfully.
        metadata = event.metadata.model_dump()
        metadata.update(
            producer="gateway",
            causation_id=event.id,
            observed_at=observed.isoformat().replace("+00:00", "Z"),
        )
        receipt = TransportReceiptV2.model_validate(
            {
                "id": str(uuid5(NAMESPACE_URL, "smartfan:receipt:" + event.id)),
                "schema_version": "2.0",
                "timestamp": observed.isoformat().replace("+00:00", "Z"),
                "tipo": "transport.received",
                "dispositivo": event.dispositivo,
                "correlation_id": event.correlation_id,
                "metadata": metadata,
                "conteudo": {"source_event_id": event.id, "status": "durably_received"},
            }
        )
        return mqtt_topic_v2(receipt), serialize_event_v2(receipt)

    def _presence(self, conn, event) -> None:
        if not isinstance(event, (DeviceStateV2, TelemetrySampleV2)):
            return
        timestamp = datetime.fromisoformat(event.timestamp)
        args = {
            "id": event.dispositivo,
            "zone": event.metadata.zone,
            "boot": event.metadata.boot_id,
            "time": timestamp,
            "seq": event.metadata.sequence,
        }
        conn.execute(
            text("""INSERT INTO transport.device_presence(device_id,zone,boot_id,boot_seen_at)
            VALUES(:id,:zone,:boot,:time) ON CONFLICT(device_id) DO UPDATE
            SET boot_id=excluded.boot_id,boot_seen_at=excluded.boot_seen_at,last_sample_at=NULL,
            state_at=NULL,last_sequence=-1,last_revision=NULL
            WHERE device_presence.boot_id<>excluded.boot_id AND device_presence.boot_seen_at<excluded.boot_seen_at
              AND COALESCE(device_presence.last_sample_at,device_presence.boot_seen_at)<excluded.boot_seen_at
              AND COALESCE(device_presence.state_at,device_presence.boot_seen_at)<excluded.boot_seen_at"""),
            args,
        )
        if isinstance(event, TelemetrySampleV2):
            conn.execute(
                text("""UPDATE transport.device_presence SET last_sample_at=:time,last_sequence=:seq,updated_at=clock_timestamp()
                WHERE device_id=:id AND boot_id=:boot AND last_sequence<:seq AND (last_sample_at IS NULL OR last_sample_at<:time)"""),
                args,
            )
        else:
            args.update(
                revision=event.conteudo.last_revision,
                mode=event.conteudo.mode,
                block=event.conteudo.manual_cooling_block,
            )
            conn.execute(
                text("""UPDATE transport.device_presence SET state_at=:time,last_revision=:revision,mode=:mode,
                manual_cooling_block=:block,updated_at=clock_timestamp()
                WHERE device_id=:id AND boot_id=:boot AND (state_at IS NULL OR state_at<:time)"""),
                args,
            )

    def has_result(self, identity: str) -> bool:
        with self.store.engine.connect() as conn:
            return (
                conn.execute(
                    text(
                        "SELECT 1 FROM transport.command_results WHERE command_id=:id"
                    ),
                    {"id": identity},
                ).scalar_one_or_none()
                is not None
            )

    def ready_for(self, command: CommandRequestedV2, now: datetime) -> bool:
        if not self.registered(command.dispositivo, command.metadata.zone, active=True):
            return False
        with self.store.engine.connect() as conn:
            row = (
                conn.execute(
                    text(
                        "SELECT boot_id,last_sample_at,last_revision FROM transport.device_presence WHERE device_id=:id"
                    ),
                    {"id": command.dispositivo},
                )
                .mappings()
                .first()
            )
        return bool(
            row
            and str(row["boot_id"]) == command.conteudo.target_boot_id
            and row["last_revision"] is not None
            and row["last_sample_at"]
            and 0 <= (now - row["last_sample_at"]).total_seconds() <= 6
        )

    def receive_command(self, payload: bytes, route: str, user_id: str | None) -> bool:
        try:
            event = parse_event_v2(payload)
            if (
                not isinstance(event, CommandRequestedV2)
                or not authenticated_publisher(event, user_id)
                or routing_key_v2(event)[1] != route
                or not self.registered(
                    event.dispositivo, event.metadata.zone, active=True
                )
                or (
                    event.metadata.producer == "control"
                    and event.conteudo.mode != "auto"
                )
            ):
                raise ValueError("Invalid command provenance")
        except ValueError:
            self.store.quarantine(payload, route[:256], "invalid_command_origin")
            return False
        return self.store.receive(event.id, payload, route) != "conflict"

    @staticmethod
    def dispatchable(command: CommandRequestedV2, now: datetime) -> bool:
        """Expiry is checked immediately before dispatch, including after restart."""
        return (
            datetime.fromisoformat(command.timestamp)
            <= now
            < datetime.fromisoformat(command.conteudo.expires_at)
        )
