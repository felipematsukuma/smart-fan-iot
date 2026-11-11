"""Generate canonical WebSocket controls and shared Python/TypeScript cases."""

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/smartfan_common/src"))
from smartfan_common.ws_protocol import (  # noqa: E402
    CLIENT_PACKET,
    SERVER_CONTROL,
    default_descriptor,
)


def clean(value):
    if isinstance(value, dict):
        return {
            key: clean(item) for key, item in value.items() if key != "discriminator"
        }
    if isinstance(value, list):
        return [clean(item) for item in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    package = ROOT / "packages/smartfan_common"
    frontend = ROOT / "web-smart-fan-iot/frontend/src/lib"
    stamp = "2026-11-08T22:00:00Z"
    identity = "33333333-3333-4333-8333-333333333333"
    frame = next(
        case["value"]
        for case in json.loads((package / "fixtures/events.v2.json").read_text())
        if case["name"] == "frame"
    )
    snapshot = {
        "type": "snapshot",
        "server_time": stamp,
        "devices": [
            default_descriptor("ac_01", "quarto", identity, stamp).model_dump()
        ],
        "events": [frame],
    }
    cases = [
        {
            "name": "authenticate",
            "kind": "client",
            "valid": True,
            "value": {"type": "authenticate", "ticket": "t" * 43, "devices": ["ac_01"]},
        },
        {
            "name": "subscribe",
            "kind": "client",
            "valid": True,
            "value": {"type": "subscribe", "devices": ["ac_01"]},
        },
        {
            "name": "ping",
            "kind": "client",
            "valid": True,
            "value": {"type": "ping", "id": identity},
        },
        {
            "name": "authenticated",
            "kind": "server",
            "valid": True,
            "value": {
                "type": "authenticated",
                "server_time": stamp,
                "heartbeat_seconds": 15,
                "stale_after_seconds": 6,
            },
        },
        {"name": "snapshot", "kind": "server", "valid": True, "value": snapshot},
        {
            "name": "backlog",
            "kind": "server",
            "valid": True,
            "value": {"type": "notice", "code": "backlog_skipped", "count": 5},
        },
        {
            "name": "jwt_not_ticket",
            "kind": "client",
            "valid": False,
            "value": {"type": "authenticate", "ticket": "x" * 400},
        },
        {
            "name": "extra_subscription",
            "kind": "client",
            "valid": False,
            "value": {
                "type": "subscribe",
                "devices": ["ac_01"],
                "role": "administrador",
            },
        },
        {
            "name": "too_many_devices",
            "kind": "client",
            "valid": False,
            "value": {"type": "subscribe", "devices": ["ac_01"] * 101},
        },
        {
            "name": "wrong_boolean",
            "kind": "server",
            "valid": False,
            "value": copy.deepcopy(snapshot),
        },
        {
            "name": "source_mismatch",
            "kind": "server",
            "valid": False,
            "value": copy.deepcopy(snapshot),
        },
    ]
    cases[-2]["value"]["devices"][0]["enabled"] = 1
    cases[-1]["value"]["events"][0]["conteudo"]["source_event_id"] = identity
    for case in cases:
        adapter = CLIENT_PACKET if case["kind"] == "client" else SERVER_CONTROL
        try:
            adapter.validate_python(case["value"])
            accepted = True
        except ValueError:
            accepted = False
        if accepted != case["valid"]:
            raise RuntimeError("Canonical case differs: " + case["name"])
    outputs = {}
    for name, adapter in [("ws-client", CLIENT_PACKET), ("ws-server", SERVER_CONTROL)]:
        schema = clean(adapter.json_schema())
        schema.update(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "$id": "urn:smartfan:" + name + ":1",
                "title": "ClientPacket" if name == "ws-client" else "ServerControl",
            }
        )
        outputs[package / ("schema/" + name + ".v1.json")] = schema
        outputs[frontend / (name + ".schema.json")] = schema
    outputs[package / "fixtures/ws.v1.json"] = cases
    outputs[frontend / "ws.fixtures.json"] = cases
    for path, value in outputs.items():
        content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise RuntimeError(
                    "Generated WebSocket file differs: " + str(path.relative_to(ROOT))
                )
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
