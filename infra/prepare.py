"""Generate local credentials and broker definitions without printing secrets."""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages/smartfan_common/src"))

from smartfan_common.routing_v2 import DLX, EVENTS, JOBS, QUEUES_V2

ROLES = ("gateway", "writer", "inference", "control", "api", "jobs-worker")
READ_QUEUES = {
    role: [q.name for q in QUEUES_V2 if q.consumer == role] for role in ROLES
}
EVENT_KEYS = {
    "gateway": r"^(telemetry\.[A-Za-z0-9_-]+\.hvac\.[A-Za-z0-9_-]+|device\.[A-Za-z0-9_-]+|ack\.[A-Za-z0-9_-]+)$",
    "writer": r"^persisted\.[A-Za-z0-9_-]+\.hvac\.[A-Za-z0-9_-]+$",
    "inference": r"^(frame\.[A-Za-z0-9_-]+|insight\.[A-Za-z0-9_-]+|model\.activated)$",
    "control": r"^(command\.[A-Za-z0-9_-]+|alert\.(info|warning|critical))$",
    "api": r"^command\.[A-Za-z0-9_-]+$",
    "jobs-worker": r"^(job\.progress|model\.available)$",
}


def rabbit_password_hash(password: str) -> str:
    salt = secrets.token_bytes(4)
    return base64.b64encode(
        salt + hashlib.sha256(salt + password.encode()).digest()
    ).decode()


def mqtt_password_hash(password: str) -> str:
    salt = secrets.token_bytes(12)
    digest = hashlib.pbkdf2_hmac("sha512", password.encode(), salt, 101)
    return (
        "$7$101$"
        + base64.b64encode(salt).decode()
        + "$"
        + base64.b64encode(digest).decode()
    )


def prepare(directory: Path) -> dict[str, int]:
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        directory.chmod(0o700)
    created = 0

    def credential(name: str) -> str:
        nonlocal created
        path = directory / name
        try:
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(secrets.token_hex(32) + "\n")
            if os.name != "nt":
                # Directory is private on the host. Individual read-only files
                # are mounted only into their intended non-root container.
                path.chmod(0o444)
            created += 1
        except FileExistsError:
            pass
        value = path.read_text(encoding="utf-8").strip()
        if len(value) < 32 or any(c.isspace() for c in value):
            raise ValueError(f"Invalid local credential file: {name}")
        return value

    passwords = {
        role: credential("rabbit_" + role)
        for role in (*ROLES, "api-monitor", "bootstrap")
    }
    for name in (
        "postgres_bootstrap",
        "influx_bootstrap",
        "influx_admin_token",
        "jwt_signing_key",
        "initial_admin_password",
        "initial_operator_password",
        "initial_viewer_password",
    ):
        credential(name)
    for role in ROLES:
        credential("postgres_" + role)
    mqtt_users = {
        role: credential("mqtt_" + role)
        for role in ("gateway", "simulator_ac_01", "health")
    }

    users = [
        {
            "name": role,
            "password_hash": rabbit_password_hash(pw),
            "hashing_algorithm": "rabbit_password_hashing_sha256",
            "tags": "administrator"
            if role == "bootstrap"
            else "monitoring"
            if role == "api-monitor"
            else "",
        }
        for role, pw in passwords.items()
    ]
    permissions = [
        {
            "user": "bootstrap",
            "vhost": "/smartfan",
            "configure": ".*",
            "write": ".*",
            "read": ".*",
        }
    ]
    topic_permissions = []
    for role in ROLES:
        queues = "^(" + "|".join(re.escape(q) for q in READ_QUEUES[role]) + ")$"
        writes = r"^smartfan\.(events|dlx" + ("|jobs" if role == "api" else "") + ")$"
        permissions.append(
            {
                "user": role,
                "vhost": "/smartfan",
                "configure": "^$",
                "write": writes,
                "read": queues,
            }
        )
        topic_permissions.append(
            {
                "user": role,
                "vhost": "/smartfan",
                "exchange": EVENTS,
                "write": EVENT_KEYS[role],
                "read": ".*",
            }
        )
        topic_permissions.append(
            {
                "user": role,
                "vhost": "/smartfan",
                "exchange": DLX,
                "write": r"^failure\." + role + "$",
                "read": ".*",
            }
        )
        if role == "api":
            topic_permissions.append(
                {
                    "user": role,
                    "vhost": "/smartfan",
                    "exchange": JOBS,
                    "write": r"^job\.(generate|train)$",
                    "read": ".*",
                }
            )
    permissions.append(
        {
            "user": "api-monitor",
            "vhost": "/smartfan",
            "configure": "^$",
            "write": "^$",
            "read": "^$",
        }
    )
    definitions = {
        "vhosts": [{"name": "/smartfan"}],
        "users": users,
        "permissions": permissions,
        "topic_permissions": topic_permissions,
        "exchanges": [
            {
                "name": name,
                "vhost": "/smartfan",
                "type": "topic",
                "durable": True,
                "auto_delete": False,
                "internal": False,
                "arguments": {},
            }
            for name in (EVENTS, JOBS, DLX)
        ],
        "queues": [
            {
                "name": q.name,
                "vhost": "/smartfan",
                "durable": True,
                "auto_delete": False,
                "arguments": {"x-queue-type": "quorum"},
            }
            for q in QUEUES_V2
        ],
        "bindings": [
            {
                "source": q.exchange,
                "vhost": "/smartfan",
                "destination": q.name,
                "destination_type": "queue",
                "routing_key": key,
                "arguments": {},
            }
            for q in QUEUES_V2
            for key in q.bindings
        ],
        "policies": [
            {
                "vhost": "/smartfan",
                "name": "durable-work",
                "pattern": r"^q\.(?!dlq$)",
                "apply-to": "quorum_queues",
                "priority": 1,
                "definition": {
                    "dead-letter-exchange": DLX,
                    "dead-letter-strategy": "at-least-once",
                    "overflow": "reject-publish",
                    "max-length-bytes": 268435456,
                    "delivery-limit": 5,
                },
            },
            {
                "vhost": "/smartfan",
                "name": "preserve-dlq",
                "pattern": r"^q\.dlq$",
                "apply-to": "quorum_queues",
                "priority": 1,
                "definition": {
                    "overflow": "reject-publish",
                    "max-length-bytes": 268435456,
                },
            },
        ],
    }

    # Generated files may be refreshed from the same retained credentials. Their
    # salts can change, credentials and active data never do.
    def generated(name: str, content: str) -> None:
        temporary = directory / (name + "." + secrets.token_hex(8) + ".tmp")
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name != "nt":
            temporary.chmod(0o444)
        temporary.replace(directory / name)

    generated("rabbitmq-definitions.json", json.dumps(definitions, indent=2) + "\n")
    generated(
        "mosquitto-passwords",
        "".join(
            f"{user}:{mqtt_password_hash(pw)}\n" for user, pw in mqtt_users.items()
        ),
    )
    return {
        "created_credentials": created,
        "queues": len(QUEUES_V2),
        "service_users": len(ROLES),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=ROOT / "secrets")
    args = parser.parse_args()
    print(json.dumps(prepare(args.directory)))


if __name__ == "__main__":
    main()
