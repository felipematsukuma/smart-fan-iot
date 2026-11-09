"""One million telemetry vectors in a disposable bucket, never live/lab data."""

import json
import math
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from smartfan_common.influx_v2 import InfluxHTTP


def main() -> None:
    headers = {
        "Authorization": "Token "
        + Path("/run/secrets/influx_admin_token").read_text().strip(),
        "Content-Type": "application/json",
    }

    def request(path, method="GET", body=None):
        req = urllib.request.Request(
            "http://influxdb:8086/api/v2/" + path,
            method=method,
            headers=headers,
            data=json.dumps(body).encode() if body else None,
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response) if response.status != 204 else None

    org = request("orgs?org=smartfan")["orgs"][0]["id"]
    name = "benchmark_" + uuid4().hex
    bucket = request(
        "buckets",
        "POST",
        {
            "orgID": org,
            "name": name,
            "retentionRules": [{"type": "expire", "everySeconds": 31 * 86400}],
        },
    )
    client = InfluxHTTP(
        Path("/run/secrets/influx_admin_token"), bucket=name, timeout=15
    )
    base = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=100000)
    base_ns = int(base.timestamp()) * 10**9
    start = time.monotonic()
    try:
        for offset in range(0, 1000000, 5000):
            lines = []
            for index in range(offset, offset + 5000):
                device = index % 10
                step = index // 10
                current = 4.0 + math.sin(step / 120) * 0.2
                raw = f"{index + 1:032x}"
                identity = f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
                lines.append(
                    f'hvac_telemetry,device_id=bench_{device:02d},zone=quarto,equipment_type=ac_split_onoff current_a={current},compressor_case_temp_c=58.0,vibration_rms_mm_s=1.2,indoor_temp_c=26.0,outdoor_temp_c=32.0,power_w=850.0,compressor_on=true,condenser_fan_on=true,event_id="{identity}",boot_id="33333333-3333-4333-8333-333333333333",sequence={step}i,received_at="{base.isoformat().replace("+00:00", "Z")}",missing_fields="" {base_ns + step * 10**9}'
                )
            client.write("\n".join(lines).encode())
            if (offset + 5000) % 100000 == 0:
                print(
                    json.dumps(
                        {
                            "written": offset + 5000,
                            "elapsed_seconds": round(time.monotonic() - start, 2),
                        }
                    ),
                    flush=True,
                )
        write_seconds = time.monotonic() - start
        count = client.query(
            f'from(bucket:{json.dumps(name)}) |> range(start:-31d) |> filter(fn:(r)=>r._measurement=="hvac_telemetry" and r._field=="event_id") |> group() |> count()'
        )
        assert len(count) == 1 and int(count[0]["_value"]) == 1000000
        stop = base + timedelta(seconds=100000)
        query = client.chart_query("bench_00", stop - timedelta(hours=24), stop)
        latencies = []
        sizes = []
        for _ in range(21):
            before = time.monotonic()
            rows = client.query(query)
            latencies.append(time.monotonic() - before)
            sizes.append(len(rows))
            assert 0 < len(rows) <= 1000
        warm = sorted(latencies[1:])
        print(
            json.dumps(
                {
                    "vectors": 1000000,
                    "equipment_count": 10,
                    "write_seconds": round(write_seconds, 3),
                    "query_first_seconds": round(latencies[0], 3),
                    "query_warm_p95_seconds": round(
                        warm[math.ceil(0.95 * len(warm)) - 1], 3
                    ),
                    "chart_points_max": max(sizes),
                    "generator_peak_rss_mib": round(
                        int(
                            next(
                                line
                                for line in Path("/proc/self/status")
                                .read_text()
                                .splitlines()
                                if line.startswith("VmHWM:")
                            ).split()[1]
                        )
                        / 1024,
                        2,
                    ),
                    "scope": "Influx capacity only; not full AMQP writer throughput; OS cache not flushed",
                }
            ),
            flush=True,
        )
    finally:
        request("buckets/" + bucket["id"], "DELETE")


if __name__ == "__main__":
    main()
