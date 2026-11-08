"""Smoke test against an active, foreground Wokwi session and the local API.

Default: read telemetry and history only. --control also requests ON/OFF and
restores the initial state. Never run against a physical appliance.
"""

import argparse
import json
import time
from urllib.request import Request, urlopen

import serial


def api(base: str, path: str, body: dict | None = None) -> dict:
    request = Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def read_telemetry(port, device_id: str, expected: bool | None = None) -> dict:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        line = port.readline().decode(errors="replace")
        if "Telemetria enviada: " not in line:
            continue
        message = json.loads(line.split("Telemetria enviada: ", 1)[1])
        if message["device_id"] == device_id and (
            expected is None or message["is_on"] is expected
        ):
            return message
    raise TimeoutError("No matching telemetry: keep Wokwi running in the foreground")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", default="esp32_fan_01")
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--serial", default="rfc2217://localhost:4000")
    parser.add_argument("--control", action="store_true")
    args = parser.parse_args()
    path = f"/api/device/{args.device}"
    original = api(args.api, path)
    with serial.serial_for_url(args.serial, baudrate=115200, timeout=1) as port:
        sample = read_telemetry(port, args.device)
        print("Telemetry:", sample["device_id"], sample["power_w"], "W")
        if args.control:
            try:
                for action, expected in [("ON", True), ("OFF", False)]:
                    api(args.api, path + "/command", {"action": action})
                    observed = read_telemetry(port, args.device, expected)
                    print(action, "confirmed by device:", observed["power_w"], "W")
            finally:
                api(
                    args.api,
                    path + "/command",
                    {"action": "ON" if original["is_on"] else "OFF"},
                )
        metrics = api(args.api, path + "/metrics?range_hours=1")
        if metrics["history_count"] == 0:
            raise AssertionError("Live telemetry has no persisted history")
        print("History:", metrics["history_count"], "samples; coverage:", metrics["coverage"])


if __name__ == "__main__":
    main()
