"""Read actual gateway/writer journals and Influx IDs in an isolated test copy."""

import json
import sys

import httpx
import psycopg2

from .probe import records


def main():
    data = json.load(sys.stdin)
    connection = psycopg2.connect(
        host="postgres",
        dbname="smartfan",
        user="smartfan_bootstrap",
        password=data["pg_password"],
        connect_timeout=5,
    )
    cursor = connection.cursor()
    cursor.execute(
        "SELECT o.event_id::text,o.sampled_at::text,g.observed_at::text,COALESCE(w.state='completed',false) FROM transport.telemetry_origins o JOIN transport.inbox g ON g.owner='gateway' AND g.event_id=o.event_id LEFT JOIN transport.inbox w ON w.owner='writer' AND w.event_id=o.event_id WHERE o.device_id=ANY(%s) ORDER BY o.event_id",
        (data["devices"],),
    )
    source = cursor.fetchall()
    cursor.execute(
        "SELECT owner,split_part(routing_key,'.',1),count(*) FROM transport.outbox WHERE state='completed' AND finished_at>=CAST(%s AS timestamptz) AND finished_at<CAST(%s AS timestamptz) GROUP BY 1,2 ORDER BY 1,2",
        (data["start"], data["stop"]),
    )
    amqp = [
        {"owner": owner, "route_prefix": prefix, "unique_messages": count}
        for owner, prefix, count in cursor.fetchall()
    ]
    cursor.execute("SELECT count(*) FROM transport.failures")
    failures = cursor.fetchone()[0]
    cursor.execute(
        "SELECT count(*) FROM transport.inbox WHERE state IN ('pending','working') AND (event_id IN (SELECT event_id FROM transport.telemetry_origins WHERE device_id=ANY(%s)) OR split_part(route,'.',-1)=ANY(%s) OR split_part(route,'/',2)=ANY(%s))",
        (data["devices"], data["devices"], data["devices"]),
    )
    inbox_pending = cursor.fetchone()[0]
    cursor.execute(
        "SELECT count(*) FROM transport.outbox WHERE state IN ('pending','working') AND split_part(routing_key,'.',-1)=ANY(%s)",
        (data["devices"],),
    )
    outbox_pending = cursor.fetchone()[0]
    cursor.close()
    connection.close()
    ids = []
    if data.get("influx", True):
        with httpx.Client(
            base_url="http://influxdb:8086",
            headers={"Authorization": "Token " + data["influx_token"]},
            timeout=30,
            trust_env=False,
        ) as client:
            flux = (
                'from(bucket:"live") |> range(start:0) |> filter(fn:(r)=>r._measurement=="hvac_telemetry" and r._field=="event_id" and contains(value:r.device_id,set:'
                + json.dumps(data["devices"])
                + ')) |> keep(columns:["_value"])'
            )
            response = client.post(
                "/api/v2/query",
                params={"org": "smartfan"},
                headers={"Accept": "text/csv"},
                json={"query": flux, "type": "flux"},
            )
            response.raise_for_status()
            ids = [row["_value"] for row in records(response.text)]
    print(
        json.dumps(
            {
                "source": source,
                "influx_ids": ids,
                "amqp": amqp,
                "failures": failures,
                "inbox_pending": inbox_pending,
                "outbox_pending": outbox_pending,
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as failure:
        print(json.dumps({"probe_error": type(failure).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
