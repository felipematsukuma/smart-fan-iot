"""Versioned administrative metadata; never edits the observed physical state."""

import json

from smartfan_common.device_registry import DeviceCreate, DeviceUpdate
from smartfan_common.ws_protocol import default_descriptor
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from .auth import Principal, audit
from .errors import Problem

UNITS = {
    "current_a": "A",
    "compressor_case_temp_c": "degC",
    "vibration_rms_mm_s": "mm/s",
    "indoor_temp_c": "degC",
    "outdoor_temp_c": "degC",
}


class DeviceRegistry:
    def __init__(self, engine: Engine):
        self.engine = engine

    def list(self, after: str = "", limit: int = 50) -> dict:
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    text("""SELECT d.*,p.boot_id,p.last_sample_at
              FROM app.device_registry d LEFT JOIN transport.device_status p ON p.device_id=d.id
              WHERE d.id>:after ORDER BY d.id LIMIT :limit"""),
                    {"after": after, "limit": limit + 1},
                )
                .mappings()
                .all()
            )
        return {
            "items": [self.public(dict(row)) for row in rows[:limit]],
            "next_cursor": rows[limit - 1]["id"] if len(rows) > limit else None,
        }

    @staticmethod
    def public(row: dict) -> dict:
        descriptor = default_descriptor(
            row["id"],
            row["zone"],
            str(row["boot_id"]) if row.get("boot_id") else None,
            row["last_sample_at"].isoformat().replace("+00:00", "Z")
            if row.get("last_sample_at")
            else None,
        )
        descriptor = descriptor.model_copy(
            update={"name": row["name"], "enabled": row["enabled"]}
        )
        return {
            **descriptor.model_dump(mode="json"),
            "revision": row["revision"],
            "profile": row["configuration"],
            "sensor_units": UNITS,
            "actuator_capabilities": {
                "compressor_on": "on_off",
                "condenser_fan_on": "on_off",
            },
        }

    def get(self, identity: str) -> dict:
        with self.engine.connect() as conn:
            row = (
                conn.execute(
                    text("""SELECT d.*,p.boot_id,p.last_sample_at FROM app.device_registry d
              LEFT JOIN transport.device_status p ON p.device_id=d.id WHERE d.id=:id"""),
                    {"id": identity},
                )
                .mappings()
                .first()
            )
        if row is None:
            raise Problem(404, "device_not_found", "Dispositivo não encontrado.")
        return self.public(dict(row))

    def create(self, body: DeviceCreate, actor: Principal, correlation: str) -> dict:
        descriptor = default_descriptor(body.id, body.zone, None, None)
        try:
            with self.engine.begin() as conn:
                conn.execute(text("SELECT pg_advisory_xact_lock(734120)"))
                if (
                    conn.execute(text("SELECT count(*) FROM app.devices")).scalar_one()
                    >= 100
                ):
                    raise Problem(
                        409,
                        "device_capacity",
                        "Limite local de 100 dispositivos atingido.",
                    )
                conn.execute(
                    text(
                        "INSERT INTO app.devices(id,name,zone,equipment_type) VALUES(:id,:name,:zone,:equipment_type)"
                    ),
                    body.model_dump(exclude={"profile"}),
                )
                conn.execute(
                    text(
                        "INSERT INTO app.device_configurations(device_id,revision,configuration,actor_user_id) VALUES(:id,1,CAST(:config AS jsonb),:actor)"
                    ),
                    {
                        "id": body.id,
                        "config": json.dumps(body.profile.model_dump()),
                        "actor": actor.id,
                    },
                )
                for field, identity in descriptor.sensor_ids.model_dump().items():
                    conn.execute(
                        text(
                            "INSERT INTO app.sensors(id,device_id,field,unit) VALUES(:id,:device,:field,:unit)"
                        ),
                        {
                            "id": identity,
                            "device": body.id,
                            "field": field,
                            "unit": UNITS[field],
                        },
                    )
                for field, identity in descriptor.actuator_ids.model_dump().items():
                    conn.execute(
                        text(
                            "INSERT INTO app.actuators(id,device_id,field,capability) VALUES(:id,:device,:field,'on_off')"
                        ),
                        {"id": identity, "device": body.id, "field": field},
                    )
                audit(
                    conn,
                    actor.id,
                    "device.created",
                    "device",
                    body.id,
                    correlation,
                    {"revision": 1},
                )
        except IntegrityError:
            raise Problem(
                409, "device_exists", "ID de dispositivo ou componente já cadastrado."
            ) from None
        return self.get(body.id)

    def update(
        self, identity: str, body: DeviceUpdate, actor: Principal, correlation: str
    ) -> dict:
        with self.engine.begin() as conn:
            row = (
                conn.execute(
                    text("SELECT * FROM app.devices WHERE id=:id FOR UPDATE"),
                    {"id": identity},
                )
                .mappings()
                .first()
            )
            if row is None:
                raise Problem(404, "device_not_found", "Dispositivo não encontrado.")
            if row["revision"] != body.expected_revision:
                raise Problem(
                    409,
                    "device_revision_conflict",
                    "O cadastro mudou. Atualize antes de salvar.",
                )
            revision = row["revision"] + 1
            profile = (
                body.profile.model_dump()
                if body.profile
                else conn.execute(
                    text(
                        "SELECT configuration FROM app.device_configurations WHERE device_id=:id AND revision=:revision"
                    ),
                    {"id": identity, "revision": row["revision"]},
                ).scalar_one()
            )
            conn.execute(
                text(
                    "INSERT INTO app.device_configurations(device_id,revision,configuration,actor_user_id) VALUES(:id,:revision,CAST(:config AS jsonb),:actor)"
                ),
                {
                    "id": identity,
                    "revision": revision,
                    "config": json.dumps(profile),
                    "actor": actor.id,
                },
            )
            conn.execute(
                text(
                    "UPDATE app.devices SET name=:name,enabled=:enabled,revision=:revision,updated_at=clock_timestamp() WHERE id=:id"
                ),
                {
                    "id": identity,
                    "name": body.name if body.name is not None else row["name"],
                    "enabled": body.enabled
                    if body.enabled is not None
                    else row["enabled"],
                    "revision": revision,
                },
            )
            audit(
                conn,
                actor.id,
                "device.updated",
                "device",
                identity,
                correlation,
                {
                    "revision": revision,
                    "fields": sorted(body.model_fields_set - {"expected_revision"}),
                },
            )
        return self.get(identity)
