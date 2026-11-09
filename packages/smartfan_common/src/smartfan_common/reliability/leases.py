"""Exclusive heavy-work leases. Expiry fences writes, never proves CPU stopped."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import Engine, text


@dataclass(frozen=True)
class ResourceToken:
    resource: str
    owner_instance_id: str
    holder_service: str
    generation: int


class ResourceLeases:
    def __init__(self, engine: Engine, service: str):
        if service not in ("api", "jobs-worker"):
            raise ValueError("Only assistant/job owners may acquire heavy resources")
        self.engine, self.service = engine, service
        with engine.connect() as conn:
            if conn.execute(text("SELECT current_user")).scalar_one() != "smartfan_" + service:
                raise PermissionError("Resource service must match authenticated database role")

    def acquire(
        self, owner_instance_id: str, kind: str, ttl_seconds: int = 30
    ) -> ResourceToken | None:
        if (self.service == "api" and kind != "chat") or (
            self.service == "jobs-worker" and kind == "chat"
        ):
            raise ValueError("Resource kind does not belong to service")
        if (
            str(UUID(owner_instance_id)) != owner_instance_id
            or kind not in ("chat", "generate", "train")
            or not 1 <= ttl_seconds <= 30
        ):
            raise ValueError("Invalid resource lease settings")
        with self.engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(734115,0)"))
            now = cast(datetime, conn.execute(text("SELECT clock_timestamp()")).scalar_one())
            row = (
                conn.execute(
                    text(
                        "SELECT * FROM transport.resource_leases WHERE resource='heavy' FOR UPDATE"
                    )
                )
                .mappings()
                .first()
            )
            if row and row["state"] != "released":
                if row["state"] == "active" and row["expires_at"] <= now:
                    conn.execute(
                        text(
                            "UPDATE transport.resource_leases SET state='recovering',updated_at=:now WHERE resource='heavy'"
                        ),
                        {"now": now},
                    )
                return None
            generation = row["generation"] + 1 if row else 1
            conn.execute(
                text("""INSERT INTO transport.resource_leases(resource,holder_service,owner_instance_id,generation,kind,state,expires_at,updated_at)
                VALUES('heavy',:service,:owner,:generation,:kind,'active',:expiry,:now)
                ON CONFLICT(resource) DO UPDATE SET holder_service=:service,owner_instance_id=:owner,generation=:generation,kind=:kind,state='active',expires_at=:expiry,updated_at=:now"""),
                {
                    "service": self.service,
                    "owner": owner_instance_id,
                    "generation": generation,
                    "kind": kind,
                    "now": now,
                    "expiry": now + timedelta(seconds=ttl_seconds),
                },
            )
            return ResourceToken("heavy", owner_instance_id, self.service, generation)

    def renew(self, token: ResourceToken, ttl_seconds: int = 30) -> bool:
        if token.holder_service != self.service or not 1 <= ttl_seconds <= 30:
            return False
        with self.engine.begin() as conn:
            now = cast(datetime, conn.execute(text("SELECT clock_timestamp()")).scalar_one())
            result = conn.execute(
                text("""UPDATE transport.resource_leases SET expires_at=:expiry,updated_at=:now
                WHERE resource=:resource AND holder_service=:service AND owner_instance_id=:owner
                AND generation=:generation AND state='active' AND expires_at>:now"""),
                {
                    "resource": token.resource,
                    "service": self.service,
                    "owner": token.owner_instance_id,
                    "generation": token.generation,
                    "now": now,
                    "expiry": now + timedelta(seconds=ttl_seconds),
                },
            )
            return result.rowcount == 1

    def valid(self, token: ResourceToken) -> bool:
        if token.holder_service != self.service:
            return False
        with self.engine.connect() as conn:
            return (
                conn.execute(
                    text("""SELECT 1 FROM transport.resource_leases WHERE resource=:resource
                AND holder_service=:service AND owner_instance_id=:owner AND generation=:generation
                AND state='active' AND expires_at>clock_timestamp()"""),
                    {
                        "resource": token.resource,
                        "service": self.service,
                        "owner": token.owner_instance_id,
                        "generation": token.generation,
                    },
                ).first()
                is not None
            )

    def release_after_confirmed_stop(self, token: ResourceToken) -> bool:
        """Only the supervisor calls this AFTER verifying process/upstream stopped.

        Losing a heartbeat is not confirmation. If the supervisor is unavailable,
        leave recovering and require explicit operational recovery.
        """
        if token.holder_service != self.service:
            return False
        with self.engine.begin() as conn:
            result = conn.execute(
                text("""UPDATE transport.resource_leases SET state='released',updated_at=clock_timestamp()
                WHERE resource=:resource AND holder_service=:service AND owner_instance_id=:owner
                AND generation=:generation AND state IN ('active','recovering')"""),
                {
                    "resource": token.resource,
                    "service": self.service,
                    "owner": token.owner_instance_id,
                    "generation": token.generation,
                },
            )
            return result.rowcount == 1
