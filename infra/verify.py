"""Run real infrastructure acceptance checks without printing credential values."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def docker(*args: str, script: str | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        input=script,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Infrastructure verification command failed; inspect service readiness"
        )
    return result


def verify() -> dict[str, object]:
    rows = [
        json.loads(line)
        for line in docker("ps", "-a", "--format", "json").stdout.splitlines()
    ]
    states = {row["Service"]: row for row in rows}
    for service in ("postgres", "influxdb", "rabbitmq", "mosquitto", "ollama"):
        assert states[service]["Health"] == "healthy", service
        assert all(
            not p.get("PublishedPort")
            for p in (states[service].get("Publishers") or [])
        ), "Default infrastructure must not expose host ports"
    for service in ("bootstrap", "ollama-init"):
        assert (
            states[service]["State"] == "exited" and states[service]["ExitCode"] == 0
        ), service
    users = json.loads(
        docker(
            "exec", "-T", "rabbitmq", "rabbitmqctl", "list_users", "--formatter", "json"
        ).stdout
    )
    assert "guest" not in {u["user"] for u in users}
    queues = json.loads(
        docker(
            "exec",
            "-T",
            "rabbitmq",
            "rabbitmqctl",
            "list_queues",
            "-p",
            "/smartfan",
            "name",
            "type",
            "--formatter",
            "json",
        ).stdout
    )
    assert len(queues) == 8 and all(q["type"] == "quorum" for q in queues)
    for topic, allowed in (
        ("health/mosquitto", True),
        ("devices/ac_01/telemetry", False),
    ):
        script = (
            'mosquitto_pub -h 127.0.0.1 -u health -P "$(cat /run/secrets/mqtt_health)" -V mqttv5 -t '
            + topic
            + " -m probe -q 1\n"
        )
        result = docker("exec", "-T", "mosquitto", "sh", script=script)
        # mosquitto_pub can exit zero on MQTT5 PUBACK Not Authorized: inspect
        # broker reason as well, otherwise this would be a false positive.
        denied = "not authorized" in (result.stdout + result.stderr).lower()
        assert denied != allowed, "MQTT ACL result differs from policy"
    anonymous = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "mosquitto",
            "mosquitto_pub",
            "-h",
            "127.0.0.1",
            "-t",
            "health/mosquitto",
            "-m",
            "anonymous",
            "-q",
            "1",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert (
        anonymous.returncode != 0
        and "not authori" in (anonymous.stdout + anonymous.stderr).lower()
    )
    return {
        "status": "passed",
        "healthy_services": 5,
        "quorum_queues": 8,
        "anonymous_mqtt": "denied",
        "mqtt_cross_topic": "denied",
        "model_init": "completed",
    }


if __name__ == "__main__":
    print(json.dumps(verify()))
