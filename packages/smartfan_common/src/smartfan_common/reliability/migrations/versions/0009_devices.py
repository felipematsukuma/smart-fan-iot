"""Device metadata and append-only configuration versions; no telemetry copied."""

import json

from alembic import op
from sqlalchemy import text

from smartfan_common.device_registry import DeviceCreate
from smartfan_common.ws_protocol import default_descriptor

revision = "0009_devices"
down_revision = "0008_source_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      CREATE TABLE app.devices (
        id varchar(32) PRIMARY KEY CHECK(id ~ '^[A-Za-z0-9_-]{1,32}$'),
        name varchar(80) NOT NULL,zone varchar(64) NOT NULL,
        equipment_type varchar(32) NOT NULL CHECK(equipment_type='ac_split_onoff'),
        enabled boolean NOT NULL DEFAULT true,revision integer NOT NULL DEFAULT 1 CHECK(revision>0),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      CREATE TABLE app.device_configurations (
        device_id varchar(32) NOT NULL REFERENCES app.devices(id),revision integer NOT NULL,
        configuration jsonb NOT NULL,actor_user_id uuid REFERENCES app.users(id),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(device_id,revision)
      );
      CREATE TABLE app.sensors (
        id varchar(64) PRIMARY KEY,device_id varchar(32) NOT NULL REFERENCES app.devices(id),
        field varchar(40) NOT NULL,unit varchar(16) NOT NULL,UNIQUE(device_id,field)
      );
      CREATE TABLE app.actuators (
        id varchar(64) PRIMARY KEY,device_id varchar(32) NOT NULL REFERENCES app.devices(id),
        field varchar(40) NOT NULL,capability varchar(16) NOT NULL CHECK(capability='on_off'),
        UNIQUE(device_id,field)
      );
      CREATE VIEW app.device_registry AS
        SELECT d.*,c.configuration FROM app.devices d JOIN app.device_configurations c
        ON c.device_id=d.id AND c.revision=d.revision;
      GRANT SELECT,INSERT,UPDATE ON app.devices TO smartfan_api;
      GRANT SELECT,INSERT ON app.device_configurations TO smartfan_api;
      GRANT SELECT,INSERT ON app.sensors,app.actuators TO smartfan_api;
      GRANT SELECT ON app.device_registry TO smartfan_api,smartfan_gateway,smartfan_control,smartfan_inference;
      GRANT SELECT ON app.sensors,app.actuators TO smartfan_control,smartfan_inference;
      CREATE INDEX devices_enabled_id ON app.devices(enabled,id);
    """)
    # Existing simulator identity is seeded once; later bootstrap never overwrites edits.
    body = DeviceCreate(id="ac_01", name="Ar-condicionado do quarto", zone="quarto")
    descriptor = default_descriptor(body.id, body.zone, None, None)
    conn = op.get_bind()
    conn.execute(
        text(
            "INSERT INTO app.devices(id,name,zone,equipment_type) VALUES(:id,:name,:zone,:equipment_type)"
        ),
        body.model_dump(exclude={"profile"}),
    )
    conn.execute(
        text(
            "INSERT INTO app.device_configurations(device_id,revision,configuration) VALUES(:id,1,CAST(:config AS jsonb))"
        ),
        {"id": body.id, "config": json.dumps(body.profile.model_dump())},
    )
    units = {
        "current_a": "A",
        "compressor_case_temp_c": "degC",
        "vibration_rms_mm_s": "mm/s",
        "indoor_temp_c": "degC",
        "outdoor_temp_c": "degC",
    }
    for field, identity in descriptor.sensor_ids.model_dump().items():
        conn.execute(
            text(
                "INSERT INTO app.sensors(id,device_id,field,unit) VALUES(:id,:device,:field,:unit)"
            ),
            {"id": identity, "device": body.id, "field": field, "unit": units[field]},
        )
    for field, identity in descriptor.actuator_ids.model_dump().items():
        conn.execute(
            text(
                "INSERT INTO app.actuators(id,device_id,field,capability) VALUES(:id,:device,:field,'on_off')"
            ),
            {"id": identity, "device": body.id, "field": field},
        )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")
