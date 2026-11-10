"""Run inside the restricted backup client; emit metadata, never token values."""

import hashlib
import json
import urllib.request
from pathlib import Path

from smartfan_common.influx_v2 import InfluxHTTP

base = "http://influx-upgrade:8086"
client = InfluxHTTP(Path("/credentials/api/token"), url=base, timeout=20)
if not client.healthy():
    raise RuntimeError("Trial database not healthy")
rows = client.query(
    'from(bucket:"live") |> range(start:0) |> filter(fn:(r)=>r._field=="power_w") |> count() |> group() |> sum()'
)
count = sum(int(row["_value"]) for row in rows)
token = Path("/run/secrets/influx_admin_token").read_text().strip()
request = urllib.request.Request(
    base + "/api/v2/authorizations", headers={"Authorization": "Token " + token}
)
with urllib.request.urlopen(request, timeout=10) as response:
    authorizations = json.load(response)["authorizations"]
for folder, description in (
    ("writer", "smartfan-writer-live-v1"),
    ("api", "smartfan-api-read-v1"),
    ("inference", "smartfan-inference-read-v1"),
):
    matches = [item for item in authorizations if item["description"] == description]
    if len(matches) != 1:
        raise RuntimeError("Scoped authorization metadata missing")
    stored = Path("/credentials/" + folder + "/token").read_text().strip()
    if (
        hashlib.sha256(stored.encode()).digest()
        != hashlib.sha256(matches[0]["token"].encode()).digest()
    ):
        raise RuntimeError("Scoped authorization binding mismatch")
print(
    json.dumps(
        {
            "health": "pass",
            "live_power_points": count,
            "scoped_tokens_verified": 3,
            "token_hashing": False,
        }
    )
)
