"""Read a quiescent stack; stdout is a private snapshot, never a console report."""

import csv
import hashlib
import io
import json
import sys
from pathlib import Path

import httpx
import psycopg2
from psycopg2 import sql


def sha(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def records(value: str) -> list[dict]:
    result, header = [], None
    for row in csv.reader(io.StringIO(value)):
        if not row or not any(row) or row[0].startswith("#"):
            continue
        if "_value" in row and "table" in row:
            header = row
            continue
        if header is None or len(row) != len(header):
            raise ValueError("Unexpected InfluxDB CSV record")
        result.append(
            {
                key: val
                for key, val in zip(header, row, strict=True)
                if key and key not in ("result", "table", "_start", "_stop")
            }
        )
    return result


def main():
    configuration = json.load(sys.stdin)
    connection = psycopg2.connect(
        host="postgres",
        dbname="smartfan",
        user="smartfan_bootstrap",
        password=configuration["pg_password"],
        connect_timeout=5,
    )
    connection.set_session(readonly=True, isolation_level="REPEATABLE READ")
    cursor = connection.cursor()
    cursor.execute(
        "SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('app','transport') OR (schemaname='public' AND tablename='alembic_version') ORDER BY schemaname,tablename"
    )
    tables = cursor.fetchall()
    snapshots = {}
    for index, (schema, name) in enumerate(tables):
        cursor.execute(
            "SELECT a.attname FROM pg_index i CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY k(attnum,position) JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum WHERE i.indisprimary AND i.indrelid=to_regclass(%s) ORDER BY k.position",
            (schema + "." + name,),
        )
        keys = [row[0] for row in cursor.fetchall()]
        ordering = (
            sql.SQL(",").join(sql.Identifier(key) for key in keys)
            if keys
            else sql.SQL("row_to_json(t)::text")
        )
        stream = connection.cursor(name="snapshot_" + str(index))
        stream.itersize = 1000
        stream.execute(
            sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY {}").format(
                sql.Identifier(schema, name), ordering
            )
        )
        digest, count = hashlib.sha256(), 0
        for (value,) in stream:
            digest.update(value.encode("utf-8") + b"\n")
            count += 1
        stream.close()
        snapshots[schema + "." + name] = {"rows": count, "sha256": digest.hexdigest()}
    cursor.execute(
        "SELECT desired_version,active_version,activation_revision,active_revision FROM app.model_selection WHERE singleton"
    )
    selection = dict(
        zip(
            (
                "desired_version",
                "active_version",
                "activation_revision",
                "active_revision",
            ),
            cursor.fetchone(),
            strict=True,
        )
    )
    cursor.execute(
        "SELECT version,manifest FROM app.models WHERE status='completed' AND approved ORDER BY version"
    )
    models = {}
    for version, manifest in cursor.fetchall():
        if (
            not version.startswith("mdl_")
            or "/" in version
            or "\\" in version
            or ".." in version
        ):
            raise ValueError("Unexpected model registry identity")
        actual = sha(Path("/artifacts/models") / version / "bundle.joblib")
        if actual != manifest["content"]["files"]["bundle.joblib"]:
            raise ValueError("Registered model bytes differ")
        models[version] = actual
    cursor.close()
    connection.rollback()
    connection.close()
    client = httpx.Client(
        base_url="http://influxdb:8086",
        headers={"Authorization": "Token " + configuration["influx_token"]},
        timeout=120,
        trust_env=False,
    )
    response = client.get("/api/v2/buckets", params={"limit": 100})
    response.raise_for_status()
    buckets = response.json()["buckets"]
    if len(buckets) >= 100:
        raise ValueError("Bucket snapshot scope incomplete")
    influx = {}
    for bucket in sorted(buckets, key=lambda item: item["name"]):
        if bucket["name"].startswith("_"):
            continue
        prefix = (
            "from(bucket:"
            + json.dumps(bucket["name"])
            + ") |> range(start:0,stop:time(v:"
            + json.dumps(configuration["snapshot_at"])
            + "))"
        )

        def query(expression):
            result = client.post(
                "/api/v2/query",
                params={"org": "smartfan"},
                headers={"Accept": "text/csv"},
                json={"query": expression, "type": "flux"},
            )
            result.raise_for_status()
            return records(result.text)

        counts = query(
            prefix
            + ' |> group(columns:["_measurement","_field"]) |> count(column:"_value") |> keep(columns:["_measurement","_field","_value"])'
        )
        counts = sorted(counts, key=lambda row: (row["_measurement"], row["_field"]))
        samples = query(prefix + ' |> sort(columns:["_time"],desc:true) |> limit(n:3)')
        canonical = sorted(
            json.dumps(row, sort_keys=True, separators=(",", ":")) for row in samples
        )
        influx[bucket["name"]] = {
            "id": bucket["id"],
            "counts": counts,
            "sample_rows": len(samples),
            "sample_sha256": hashlib.sha256("\n".join(canonical).encode()).hexdigest(),
        }
    client.close()
    print(
        json.dumps(
            {
                "tables": snapshots,
                "influx": influx,
                "selection": selection,
                "models": models,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as failure:
        print(json.dumps({"probe_error": type(failure).__name__}), file=sys.stderr)
        raise SystemExit(1) from None
