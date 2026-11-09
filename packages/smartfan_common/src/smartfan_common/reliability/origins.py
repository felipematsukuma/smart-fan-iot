"""Immutable source identities recorded in the gateway's reception transaction."""

from sqlalchemy import Connection, text

from ..contracts_v2 import TelemetrySampleV2
from ..provenance_v2 import telemetry_digest


def record_origin(conn: Connection, event: TelemetrySampleV2) -> None:
    conn.execute(
        text("""INSERT INTO transport.telemetry_origins(event_id,sampled_at,device_id,boot_id,sequence,data_sha256,zone)
        VALUES(:id,CAST(:stamp AS timestamptz),:device,:boot,:seq,:hash,:zone) ON CONFLICT(event_id) DO NOTHING"""),
        {
            "id": event.id,
            "stamp": event.timestamp,
            "device": event.dispositivo,
            "boot": event.metadata.boot_id,
            "seq": event.metadata.sequence,
            "hash": telemetry_digest(event.conteudo),
            "zone": event.metadata.zone,
        },
    )
