"""Deterministic HVAC points and bounded HTTP access to InfluxDB OSS 2."""

import csv
import hashlib
import io
import json
import math
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .contracts_v2 import TelemetrySampleV2


def timestamp_ns(value: str) -> int:
    stamp = datetime.fromisoformat(value)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = stamp - epoch
    return (delta.days * 86400 + delta.seconds) * 10**9 + delta.microseconds * 1000


def telemetry_point(event: TelemetrySampleV2, observed_at: datetime) -> tuple[str, bytes]:
    # Identifiers are restricted by the shared schema, so no arbitrary tag syntax.
    series = f"hvac_telemetry,device_id={event.dispositivo},zone={event.metadata.zone},equipment_type={event.metadata.equipment_type}"
    fields: dict[str, str | int | float | bool] = {
        "event_id": event.id,
        "boot_id": event.metadata.boot_id,
        "sequence": event.metadata.sequence,
        "received_at": observed_at.isoformat().replace("+00:00", "Z"),
        "missing_fields": ",".join(sorted(event.conteudo.quality.missing_fields)),
        **event.conteudo.actuators.model_dump(),
    }
    fields.update(
        {
            key: float(value)
            for key, value in event.conteudo.readings.model_dump().items()
            if value is not None
        }
    )

    def encode(value: str | int | float | bool) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value) + "i"
        if isinstance(value, float):
            return repr(value)
        return json.dumps(value, ensure_ascii=False)

    stamp = timestamp_ns(event.timestamp)
    identity = f"{series} {stamp}"
    line = (
        f"{series} "
        + ",".join(f"{key}={encode(value)}" for key, value in sorted(fields.items()))
        + f" {stamp}"
    )
    return hashlib.sha256(identity.encode()).hexdigest(), line.encode()


class InfluxHTTP:
    def __init__(
        self,
        token_file: Path,
        url: str = "http://influxdb:8086",
        org: str = "smartfan",
        timeout: float = 3,
        bucket: str = "live",
    ):
        self.url, self.org, self.timeout = url.rstrip("/"), org, timeout
        self._token = token_file.read_text().strip()
        self.bucket = bucket

    def healthy(self) -> bool:
        try:
            with urllib.request.urlopen(self.url + "/health", timeout=self.timeout) as response:
                return bool(
                    response.status == 200
                    and json.loads(response.read(65536)).get("status") == "pass"
                )
        except (OSError, ValueError):
            return False

    def write(self, lines: bytes, bucket: str | None = None) -> None:
        if len(lines) > 16 * 1024 * 1024:
            raise ValueError("Write batch exceeds memory budget")
        query = urllib.parse.urlencode(
            {"org": self.org, "bucket": bucket or self.bucket, "precision": "ns"}
        )
        request = urllib.request.Request(
            self.url + "/api/v2/write?" + query,
            data=lines,
            method="POST",
            headers={
                "Authorization": "Token " + self._token,
                "Content-Type": "text/plain; charset=utf-8",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            if response.status != 204:
                raise RuntimeError("Unexpected InfluxDB write result")

    def query(self, flux: str) -> list[dict[str, str]]:
        request = urllib.request.Request(
            self.url + "/api/v2/query?" + urllib.parse.urlencode({"org": self.org}),
            data=flux.encode(),
            method="POST",
            headers={
                "Authorization": "Token " + self._token,
                "Content-Type": "application/vnd.flux",
                "Accept": "application/csv",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read(8 * 1024 * 1024 + 1)
        if len(body) > 8 * 1024 * 1024:
            raise ValueError("Query exceeds response budget")
        rows = []
        header = None
        for row in csv.reader(io.StringIO(body.decode())):
            if not row or row[0].startswith("#"):
                continue
            if len(row) > 2 and row[1] == "result" and row[2] == "table":
                header = row
            elif header is not None:
                rows.append(dict(zip(header, row, strict=True)))
        return rows

    def energy_query(self, device_id: str, start: datetime, stop: datetime) -> str:
        self.history_query(device_id, start, stop)
        begin = start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        end = stop.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        return f"""from(bucket:{json.dumps(self.bucket)})
          |> range(start:time(v:{json.dumps(begin)}),stop:time(v:{json.dumps(end)}))
          |> filter(fn:(r)=>r._measurement=="hvac_telemetry" and r.device_id=={json.dumps(device_id)})
          |> filter(fn:(r)=>r._field=="power_w" or r._field=="boot_id")
          |> pivot(rowKey:["_time","device_id","zone","equipment_type"],columnKey:["_field"],valueColumn:"_value")
          |> group() |> sort(columns:["_time"])
          |> reduce(identity:{{energy_wh:0.0,covered_seconds:0.0,total_samples:0,missing_samples:0,discarded_intervals:0,previous_ns:0,previous_power:0.0,previous_boot:"",previous_valid:false}},fn:(r,accumulator)=>{{
            valid=exists r.power_w
            gap=float(v:int(v:r._time)-accumulator.previous_ns)/1000000000.0
            contiguous=valid and accumulator.previous_valid and r.boot_id==accumulator.previous_boot and gap>0.0 and gap<=6.0
            return {{energy_wh:accumulator.energy_wh+(if contiguous then (accumulator.previous_power+r.power_w)*0.5*gap/3600.0 else 0.0),
              covered_seconds:accumulator.covered_seconds+(if contiguous then gap else 0.0),total_samples:accumulator.total_samples+1,
              missing_samples:accumulator.missing_samples+(if valid then 0 else 1),
              discarded_intervals:accumulator.discarded_intervals+(if valid and accumulator.previous_valid and not contiguous then 1 else 0),
              previous_ns:int(v:r._time),previous_power:if valid then r.power_w else 0.0,previous_boot:r.boot_id,previous_valid:valid}}
          }})"""

    def history_query(
        self,
        device_id: str,
        start: datetime,
        stop: datetime,
        limit: int = 1000,
        after: tuple[datetime, str, str] | None = None,
    ) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", device_id) or not 1 <= limit <= 1000:
            raise ValueError("Invalid bounded history request")
        if (
            start.tzinfo is None
            or stop.tzinfo is None
            or not start < stop
            or (stop - start).total_seconds() > 31 * 86400
        ):
            raise ValueError("History requires an aware interval of at most 31 days")
        begin = start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        end = stop.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        cursor = ""
        if after is not None:
            stamp, zone, equipment = after
            if (
                stamp.tzinfo is None
                or not start <= stamp < stop
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", zone)
                or equipment != "ac_split_onoff"
            ):
                raise ValueError("Invalid history cursor")
            at = (
                "time(v:"
                + json.dumps(stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"))
                + ")"
            )
            z = json.dumps(zone)
            eq = json.dumps(equipment)
            cursor = f" |> filter(fn:(r)=>r._time>{at} or (r._time=={at} and (r.zone>{z} or (r.zone=={z} and r.equipment_type>{eq}))))"
        return f'from(bucket:{json.dumps(self.bucket)}) |> range(start:time(v:{json.dumps(begin)}),stop:time(v:{json.dumps(end)})) |> filter(fn:(r)=>r._measurement=="hvac_telemetry" and r.device_id=={json.dumps(device_id)}) |> pivot(rowKey:["_time","device_id","zone","equipment_type"],columnKey:["_field"],valueColumn:"_value") |> group(){cursor} |> sort(columns:["_time","zone","equipment_type"]) |> limit(n:{limit})'

    def chart_query(
        self, device_id: str, start: datetime, stop: datetime, max_points: int = 1000
    ) -> str:
        # Reuse the bounded identifier/time validation without issuing a query.
        self.history_query(device_id, start, stop, max_points)
        step = max(1, math.ceil((stop - start).total_seconds() / max(1, max_points - 1)))
        begin = start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        end = stop.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        fields = [
            "current_a",
            "compressor_case_temp_c",
            "vibration_rms_mm_s",
            "indoor_temp_c",
            "outdoor_temp_c",
            "power_w",
        ]
        field_filter = " or ".join("r._field==" + json.dumps(field) for field in fields)
        return f'from(bucket:{json.dumps(self.bucket)}) |> range(start:time(v:{json.dumps(begin)}),stop:time(v:{json.dumps(end)})) |> filter(fn:(r)=>r._measurement=="hvac_telemetry" and r.device_id=={json.dumps(device_id)}) |> filter(fn:(r)=>{field_filter}) |> aggregateWindow(every:{step}s,fn:mean,createEmpty:true) |> pivot(rowKey:["_time","device_id","zone","equipment_type"],columnKey:["_field"],valueColumn:"_value") |> group() |> sort(columns:["_time"]) |> limit(n:{max_points})'
