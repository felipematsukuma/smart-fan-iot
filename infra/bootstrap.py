"""Verify real broker topology and initialize isolated AIoT lab bucket."""

import base64
import json
import time
import urllib.request
from pathlib import Path

from smartfan_common.reliability.database import engine_for
from smartfan_common.routing_v2 import QUEUES_V2

from infra.database import provision_database
from infra.influx_credentials import provision_token, provision_writer
from services.api.auth import seed_users


def request(url: str, headers: dict[str, str], value: dict | None = None):
    data = json.dumps(value).encode() if value is not None else None
    req = urllib.request.Request(
        url, data=data, headers={**headers, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.load(response)


def main() -> None:
    database_engine = engine_for("bootstrap", Path("/run/secrets/postgres_bootstrap"))
    try:
        provision_database(database_engine, Path("/run/secrets"))
        seed_users(database_engine, Path("/run/secrets"))
    finally:
        database_engine.dispose()
    password = Path("/run/secrets/rabbit_bootstrap").read_text().strip()
    rabbit_headers = {
        "Authorization": "Basic "
        + base64.b64encode(("bootstrap:" + password).encode()).decode()
    }
    for _attempt in range(30):
        try:
            queues = request(
                "http://rabbitmq:15672/api/queues/%2Fsmartfan", rabbit_headers
            )
            if {q["name"] for q in queues} == {q.name for q in QUEUES_V2}:
                break
        except OSError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("RabbitMQ topology did not become ready")
    assert all(q["type"] == "quorum" for q in queues)
    users = request("http://rabbitmq:15672/api/users", rabbit_headers)
    assert "guest" not in {u["name"] for u in users}, "Guest must not exist"
    token = Path("/run/secrets/influx_admin_token").read_text().strip()
    influx_headers = {"Authorization": "Token " + token}
    orgs = request("http://influxdb:8086/api/v2/orgs?org=smartfan", influx_headers)[
        "orgs"
    ]
    assert len(orgs) == 1
    buckets = request(
        "http://influxdb:8086/api/v2/buckets?org=smartfan", influx_headers
    )["buckets"]
    if not any(b["name"] == "lab" for b in buckets):
        request(
            "http://influxdb:8086/api/v2/buckets",
            influx_headers,
            {
                "orgID": orgs[0]["id"],
                "name": "lab",
                "retentionRules": [{"type": "expire", "everySeconds": 604800}],
            },
        )
    live = next(b for b in buckets if b["name"] == "live")
    provision_writer(
        influx_headers, orgs[0]["id"], live["id"], Path("/credentials/writer")
    )
    buckets = request(
        "http://influxdb:8086/api/v2/buckets?org=smartfan", influx_headers
    )["buckets"]
    lab = next(bucket for bucket in buckets if bucket["name"] == "lab")
    provision_token(
        influx_headers,
        orgs[0]["id"],
        [(live["id"], "read"), (lab["id"], "read")],
        Path("/credentials/api"),
        "smartfan-api-read-v1",
    )
    provision_token(
        influx_headers,
        orgs[0]["id"],
        [(live["id"], "read")],
        Path("/credentials/inference"),
        "smartfan-inference-read-v1",
    )
    print(
        json.dumps(
            {
                "service": "bootstrap",
                "status": "ready",
                "queues": len(queues),
                "buckets": ["live", "lab"],
            }
        )
    )


if __name__ == "__main__":
    main()
