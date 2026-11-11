"""Private offline backups and restores into new volumes on this computer."""

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from websockets.sync.client import connect

from .common import (
    BACKUPS,
    PROJECT,
    PYTHON_IMAGE,
    ROOT,
    atomic_json,
    bounded,
    compose,
    containers,
    digest,
    docker,
    exclusive,
    private,
    ready,
)

HERE = Path(__file__).resolve().parent


def stamp():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def mount_source(config: dict, service: str, target: str) -> Path:
    source = Path(
        next(
            item["source"]
            for item in config["services"][service]["volumes"]
            if item["type"] == "bind" and item["target"] == target
        )
    ).resolve()
    if not source.is_relative_to(ROOT.resolve()) or not source.is_file():
        raise ValueError("Unexpected credential/configuration bind source")
    return source


def volume_name(config: dict, name: str):
    return config["volumes"][name]["name"]


def check_owned(name: str, project: str, logical: str):
    row = json.loads(docker("volume", "inspect", name))[0]
    labels = row.get("Labels") or {}
    if (
        labels.get("com.docker.compose.project") != project
        or labels.get("com.docker.compose.volume") != logical
    ):
        raise ValueError("Volume ownership does not match this project")


def helper(
    volume: str,
    mode: str,
    uid: int = 10001,
    gid: int = 10001,
    metadata: dict | None = None,
):
    command = [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "256m",
        "--cpus",
        "1",
        "--user",
        f"{uid}:{gid}",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
    ]
    if mode == "restore":
        command += [
            "--cap-add",
            "CHOWN",
            "-i",
            "--mount",
            "type=volume,src=" + volume + ",dst=/target",
        ]
    else:
        command += ["--mount", "type=volume,src=" + volume + ",dst=/source,readonly"]
    command += [
        "--mount",
        "type=bind,src="
        + str(HERE / "volume_archive.py")
        + ",dst=/archive.py,readonly",
        PYTHON_IMAGE,
        "python",
        "/archive.py",
        mode,
    ]
    if metadata is not None:
        command += ["--metadata", json.dumps(metadata, separators=(",", ":"))]
    return command


def metadata(volume: str) -> dict:
    owner = subprocess.run(
        helper(volume, "owner"), capture_output=True, text=True, check=True
    )
    identity = json.loads(owner.stdout)
    if not 0 < identity["uid"] < 65536 or not 0 < identity["gid"] < 65536:
        raise ValueError("Uninitialized or unsupported volume ownership")
    result = subprocess.run(
        helper(volume, "inspect", **identity), capture_output=True, text=True
    )
    if result.returncode:
        raise RuntimeError("Cannot inspect a complete volume as its non-root owner")
    return json.loads(result.stdout)


def archive_volume(volume: str, path: Path, expected: dict):
    result = hashlib.sha256()
    written = 0
    notified = time.monotonic()
    process = subprocess.Popen(
        helper(volume, "backup", expected["uid"], expected["gid"]),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    with path.open("xb") as destination:
        os.chmod(path, 0o600)
        while block := process.stdout.read(1024 * 1024):
            destination.write(block)
            result.update(block)
            written += len(block)
            if time.monotonic() - notified >= 10:
                print(
                    json.dumps(
                        {
                            "phase": "archive",
                            "volume": volume,
                            "compressed_bytes": written,
                        }
                    ),
                    flush=True,
                )
                notified = time.monotonic()
        destination.flush()
        os.fsync(destination.fileno())
    diagnostic = process.stderr.read().decode("utf-8", errors="replace")
    process.wait()
    marker = "SMARTFAN_VOLUME_META "
    lines = [
        line[len(marker) :]
        for line in diagnostic.splitlines()
        if line.startswith(marker)
    ]
    if process.returncode or len(lines) != 1 or json.loads(lines[0]) != expected:
        raise RuntimeError(
            "Archive failed or the offline source changed; raw diagnostics withheld"
        )
    return {
        "filename": path.name,
        "sha256": result.hexdigest(),
        "compressed_bytes": written,
        **expected,
    }


def source_credentials(config: dict):
    return {
        "pg_password": mount_source(
            config, "postgres", "/run/secrets/postgres_bootstrap"
        )
        .read_text()
        .strip(),
        "influx_token": mount_source(
            config, "influxdb", "/run/secrets/influx_admin_token"
        )
        .read_text()
        .strip(),
    }


def probe(config: dict, snapshot_at: str, project: str = PROJECT):
    payload = {**source_credentials(config), "snapshot_at": snapshot_at}
    network = config["networks"]["data_net"].get("name", project + "_data_net")
    image = config["services"]["bootstrap"]["image"]
    output = docker(
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--tmpfs",
        "/tmp",
        "--memory",
        "384m",
        "--cpus",
        "1",
        "--network",
        network,
        "--mount",
        "type=volume,src="
        + volume_name(config, "artifacts")
        + ",dst=/artifacts,readonly",
        "--mount",
        "type=bind,src=" + str(HERE / "probe.py") + ",dst=/probe.py,readonly",
        image,
        "python",
        "/probe.py",
        data=json.dumps(payload),
    )
    return json.loads(output)


def psql(container: str, statement: str):
    return docker(
        "exec",
        container,
        "psql",
        "-U",
        "smartfan_bootstrap",
        "-d",
        "smartfan",
        "-tAc",
        statement,
    )


def login(config: dict, url: str, password_file: Path | None = None):
    password = (
        (
            password_file
            or mount_source(config, "bootstrap", "/run/secrets/initial_admin_password")
        )
        .read_text(encoding="utf-8")
        .strip()
    )
    with httpx.Client(base_url=url, timeout=5, trust_env=False) as client:
        response = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": password}
        )
        if response.status_code != 200:
            raise RuntimeError(
                "Web verification requires the current private administrator password file"
            )
        return response.json()["access_token"]


def web_check(
    config: dict,
    url: str,
    expected_version: str | None,
    previous_token: str | None,
    password_file: Path | None,
):
    with httpx.Client(base_url=url, timeout=5, trust_env=False) as client:
        previous_rejected = None
        if previous_token:
            previous_rejected = (
                client.get(
                    "/api/v1/auth/me",
                    headers={"Authorization": "Bearer " + previous_token},
                ).status_code
                == 401
            )
            if not previous_rejected:
                raise RuntimeError("A session from before restore was accepted")
        token = login(config, url, password_file)
        headers = {"Authorization": "Bearer " + token, "Origin": url}
        try:
            response = client.get("/api/v1/devices", headers=headers)
            response.raise_for_status()
            enabled = [
                item["id"] for item in response.json()["items"] if item["enabled"]
            ]
            if not enabled:
                return {
                    "web_verified": True,
                    "previous_session_rejected": previous_rejected,
                    "live_model_verified": False,
                    "reason": "no_enabled_device",
                }
            device = "ac_01" if "ac_01" in enabled else enabled[0]
            ticket = client.post(
                "/api/v1/auth/ws-ticket", headers=headers, json={"devices": [device]}
            )
            ticket.raise_for_status()
            with connect(
                url.replace("http://", "ws://") + "/ws",
                origin=url,
                open_timeout=5,
                proxy=None,
            ) as stream:
                stream.send(
                    json.dumps(
                        {
                            "type": "authenticate",
                            "ticket": ticket.json()["ticket"],
                            "devices": [device],
                        }
                    )
                )
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    try:
                        message = json.loads(stream.recv(timeout=5))
                    except TimeoutError:
                        continue
                    if message.get("type") == "ping":
                        stream.send(json.dumps({"type": "pong", "id": message["id"]}))
                    events = (
                        message.get("events", [])
                        if message.get("type") == "snapshot"
                        else [message]
                    )
                    for event in events:
                        if (
                            event.get("tipo") != "frame.ready"
                            or event.get("dispositivo") != device
                        ):
                            continue
                        age = (
                            datetime.now(UTC)
                            - datetime.fromisoformat(event["timestamp"])
                        ).total_seconds()
                        insight = event["conteudo"]["insight"]
                        if (
                            -1 <= age <= 6
                            and insight.get("model_version") == expected_version
                        ):
                            return {
                                "web_verified": True,
                                "previous_session_rejected": previous_rejected,
                                "live_model_verified": bool(expected_version),
                                "fresh_frame_age_seconds": round(age, 3),
                            }
                raise RuntimeError(
                    "No fresh frame from the registered model after restore"
                )
        finally:
            client.post("/api/v1/auth/logout", headers=headers, json={})


def resume(services: list[str]):
    rows = containers()
    order = (
        "postgres",
        "influxdb",
        "rabbitmq",
        "mosquitto",
        "ollama",
        "gateway",
        "writer",
        "control",
        "simulator",
        "inference",
        "api",
        "jobs-worker",
        "frontend",
    )
    for service in order:
        if service not in services:
            continue
        docker("start", rows[service]["Id"])
        if "Healthcheck" in rows[service]["Config"]:
            ready(services=(service,))


def backup(resume_source: bool = True) -> Path:
    started = time.monotonic()
    config = json.loads(compose("config", "--format", "json"))
    rows = containers()
    if not {"postgres", "influxdb", "api", "frontend"} <= rows.keys():
        raise ValueError("Initialize the default project before backing it up")
    running = [service for service, row in rows.items() if row["State"]["Running"]]
    identity = uuid4().hex
    directory = bounded(
        BACKUPS / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + identity[:12])
    )
    private(directory)
    try:
        for service in ("frontend", "api"):
            if rows[service]["State"]["Running"]:
                docker("stop", rows[service]["Id"])
        docker("start", rows["postgres"]["Id"])
        ready(services=("postgres",))
        if (
            psql(
                rows["postgres"]["Id"],
                "SELECT count(*) FROM app.jobs WHERE status IN ('queued','running');",
            )
            != "0"
        ):
            raise ValueError("Finish or cancel queued/running jobs before backup")
        for service, row in rows.items():
            if service not in ("postgres", "influxdb") and row["State"]["Running"]:
                docker("stop", row["Id"])
        docker("start", rows["influxdb"]["Id"])
        ready()
        audit_id, correlation = str(uuid4()), str(uuid4())
        psql(
            rows["postgres"]["Id"],
            f"INSERT INTO app.audit(id,action,entity_type,entity_id,correlation_id,details,outcome) VALUES('{audit_id}','system.backup.started','backup','{identity}','{correlation}','{{}}'::jsonb,'success');",
        )
        snapshot_at = stamp()
        snapshot = probe(config, snapshot_at)
        compose("stop")
        if any(row["State"]["Running"] for row in containers().values()):
            raise ValueError("Every source service must stop before archiving")
        plan = {}
        for logical, item in config["volumes"].items():
            name = item["name"]
            check_owned(name, PROJECT, logical)
            plan[logical] = {"source": name, "metadata": metadata(name)}
        if (
            shutil.disk_usage(directory).free
            < sum(row["metadata"]["bytes"] for row in plan.values()) + 1024**3
        ):
            raise ValueError("Insufficient host disk space for backup")
        images = {}
        for index, reference in enumerate(
            sorted({item["image"] for item in config["services"].values()})
        ):
            image = json.loads(docker("image", "inspect", reference))[0]["Id"]
            alias = f"smartfan-backup:{identity[:12]}-{index}"
            docker("image", "tag", reference, alias)
            images[alias] = {"image_id": image, "source_reference": reference}
            for service in config["services"].values():
                if service["image"] == reference:
                    service["image"] = alias
                    service.pop("build", None)
                    service["pull_policy"] = "never"
        binds = {}
        for service in config["services"].values():
            for item in service.get("volumes", []):
                if item["type"] != "bind":
                    continue
                source = Path(item["source"]).resolve()
                if (
                    not source.is_relative_to(ROOT.resolve())
                    or not source.is_file()
                    or source.is_symlink()
                ):
                    raise ValueError(
                        "Backup supports only regular configuration/credential binds within the project"
                    )
                relative = source.relative_to(ROOT.resolve())
                destination = directory / "binds" / relative
                if str(relative) not in binds:
                    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    shutil.copy2(source, destination)
                    binds[str(relative)] = {
                        "filename": destination.relative_to(directory).as_posix(),
                        "sha256": digest(destination),
                    }
                item["source"] = str(destination)
        volumes = {}
        for logical, item in plan.items():
            print(
                json.dumps(
                    {
                        "phase": "archive_start",
                        "volume": logical,
                        "uncompressed_bytes": item["metadata"]["bytes"],
                    }
                ),
                flush=True,
            )
            volumes[logical] = {
                "source": item["source"],
                **archive_volume(
                    item["source"], directory / (logical + ".tar.gz"), item["metadata"]
                ),
            }
        atomic_json(directory / "compose.snapshot.json", config)
        manifest = {
            "schema_version": 1,
            "backup_id": identity,
            "source_project": PROJECT,
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "operator_sha256": digest(Path(__file__)),
            "snapshot_at": snapshot_at,
            "completed_at": stamp(),
            "seconds": round(time.monotonic() - started, 3),
            "original_running": running,
            "images": images,
            "binds": binds,
            "volumes": volumes,
            "snapshot": snapshot,
            "compose_sha256": digest(directory / "compose.snapshot.json"),
        }
        atomic_json(directory / "manifest.json", manifest)
        print(
            json.dumps(
                {
                    "phase": "backup_complete",
                    "path": str(directory),
                    "seconds": manifest["seconds"],
                    "volumes": len(volumes),
                }
            ),
            flush=True,
        )
        return directory
    finally:
        compose("stop")
        if resume_source:
            resume(running)


def validate(directory: Path):
    directory = bounded(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != 1
        or manifest.get("source_project") != PROJECT
        or not re.fullmatch(r"[a-f0-9]{32}", manifest.get("backup_id", ""))
    ):
        raise ValueError("Unsupported backup identity")
    if digest(directory / "compose.snapshot.json") != manifest["compose_sha256"]:
        raise ValueError("Snapshot configuration checksum differs")
    config = json.loads(
        (directory / "compose.snapshot.json").read_text(encoding="utf-8")
    )
    if set(config["volumes"]) != set(manifest["volumes"]):
        raise ValueError("Every source volume must have its own restore archive")
    if {service["image"] for service in config["services"].values()} != set(
        manifest["images"]
    ):
        raise ValueError("Every restore image must be part of the recorded snapshot")
    for logical, record in manifest["volumes"].items():
        if (
            not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", logical)
            or record["source"] != config["volumes"][logical]["name"]
        ):
            raise ValueError("Source volume identity differs from the snapshot")
        if (
            any(
                type(record[key]) is not int or not 0 < record[key] < 65536
                for key in ("uid", "gid")
            )
            or type(record["bytes"]) is not int
            or record["bytes"] < 0
            or type(record["members"]) is not int
            or record["members"] < 1
        ):
            raise ValueError("Unsupported volume metadata")
    for network in config["networks"].values():
        if network.get("external"):
            raise ValueError("External networks are outside this restore contract")
    for service in config["services"].values():
        if service.get("build") or service.get("pull_policy") != "never":
            raise ValueError("Restore must use only the preserved local images")
        for item in service.get("volumes", []):
            if (
                item["type"] == "volume"
                and item.get("source") not in manifest["volumes"]
            ):
                raise ValueError("Unrecorded named or anonymous volume mount")
            if item["type"] == "bind" and not Path(
                item["source"]
            ).resolve().is_relative_to(directory):
                raise ValueError("Restore bind source escapes the private snapshot")
    for record in [*manifest["binds"].values(), *manifest["volumes"].values()]:
        path = (directory / record["filename"]).resolve()
        if (
            not path.is_relative_to(directory)
            or not path.is_file()
            or digest(path) != record["sha256"]
        ):
            raise ValueError("Backup file missing, outside scope or corrupted")
    for reference, row in manifest["images"].items():
        if (
            json.loads(docker("image", "inspect", reference))[0]["Id"]
            != row["image_id"]
        ):
            raise ValueError("Cached backup image changed or is unavailable")
    return directory, manifest


def restore(
    directory: Path,
    port: int = 18080,
    verify_web: bool = False,
    previous_token: str | None = None,
    password_file: Path | None = None,
):
    started = time.monotonic()
    directory, manifest = validate(directory)
    if any(row["State"]["Running"] for row in containers().values()):
        raise ValueError("Stop the original project before restore on this machine")
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", port))
    project = "smartfan-restore-" + uuid4().hex[:12]
    config = copy.deepcopy(
        json.loads((directory / "compose.snapshot.json").read_text(encoding="utf-8"))
    )
    config["name"] = project
    for network in config["networks"].values():
        if network.get("external"):
            raise ValueError("External networks are outside this restore contract")
        network.pop("name", None)
    for logical, record in manifest["volumes"].items():
        name = project + "_" + logical
        docker(
            "volume",
            "create",
            "--label",
            "com.docker.compose.project=" + project,
            "--label",
            "com.docker.compose.volume=" + logical,
            "--label",
            "smartfan.restore.backup=" + manifest["backup_id"],
            name,
        )
        config["volumes"][logical] = {"external": True, "name": name}
        print(json.dumps({"phase": "restore_volume", "volume": logical}), flush=True)
        with (directory / record["filename"]).open("rb") as source:
            result = subprocess.run(
                helper(
                    name,
                    "restore",
                    0,
                    0,
                    {key: record[key] for key in ("uid", "gid", "bytes", "members")},
                ),
                stdin=source,
                capture_output=True,
            )
        if result.returncode:
            raise RuntimeError("Restore helper failed; source and backup are unchanged")
    for service in config["services"].values():
        service.pop("container_name", None)
        for item in service.get("volumes", []):
            if item["type"] == "bind" and not Path(
                item["source"]
            ).resolve().is_relative_to(directory):
                raise ValueError("Restore bind source escapes the private snapshot")
        if service.get("ports") and service is not config["services"]["frontend"]:
            raise ValueError("Only the frontend may publish a restore port")
    config["services"]["frontend"]["ports"] = [
        {
            "target": 8080,
            "published": str(port),
            "host_ip": "127.0.0.1",
            "protocol": "tcp",
        }
    ]
    config["services"]["api"].setdefault("environment", {})["WEB_ORIGINS"] = (
        f"http://127.0.0.1:{port},http://localhost:{port}"
    )
    path = directory / (project + ".json")
    atomic_json(path, config)
    compose(
        "up", "-d", "--no-build", "postgres", "influxdb", config=path, project=project
    )
    ready(project)
    observed = probe(config, manifest["snapshot_at"], project)
    if observed != manifest["snapshot"]:
        raise ValueError(
            "Restored database rows, telemetry samples or model bytes differ"
        )
    pg = containers(project)["postgres"]["Id"]
    audit_id, correlation = str(uuid4()), str(uuid4())
    psql(
        pg,
        f"BEGIN; UPDATE app.sessions SET revoked_at=clock_timestamp() WHERE revoked_at IS NULL; UPDATE app.ws_tickets SET consumed_at=clock_timestamp() WHERE consumed_at IS NULL; INSERT INTO app.audit(id,action,entity_type,entity_id,correlation_id,details,outcome) VALUES('{audit_id}','system.restore.data_verified','backup','{manifest['backup_id']}','{correlation}','{{}}'::jsonb,'success'); COMMIT;",
    )
    compose("up", "-d", "--no-build", config=path, project=project)
    ready(
        project,
        services=(
            "postgres",
            "influxdb",
            "rabbitmq",
            "mosquitto",
            "ollama",
            "gateway",
            "writer",
            "control",
            "simulator",
            "inference",
            "api",
            "jobs-worker",
            "frontend",
        ),
    )
    web_result = (
        web_check(
            config,
            f"http://127.0.0.1:{port}",
            observed["selection"]["active_version"],
            previous_token,
            password_file,
        )
        if verify_web
        else {"web_verified": False}
    )
    report = {
        "backup_id": manifest["backup_id"],
        "project": project,
        "config": str(path),
        "measured_at": stamp(),
        "seconds": round(time.monotonic() - started, 3),
        "tables_matched": len(observed["tables"]),
        "telemetry_buckets_matched": len(observed["influx"]),
        "registered_models_verified": len(observed["models"]),
        "active_version": observed["selection"]["active_version"],
        "sessions_revoked": True,
        "only_frontend_published": True,
        "url": f"http://127.0.0.1:{port}",
        **web_result,
        "passed": True,
    }
    atomic_json(directory / (project + ".report.json"), report)
    print(json.dumps({"phase": "restore_complete", **report}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("backup", "restore", "trial"))
    parser.add_argument("directory", type=Path, nargs="?")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--leave-stopped", action="store_true")
    parser.add_argument("--verify-web", action="store_true")
    parser.add_argument("--password-file", type=Path)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise ValueError("Choose a local unprivileged frontend port")
    if args.action == "backup":
        backup(not args.leave_stopped)
    elif args.action == "restore":
        if args.directory is None:
            raise ValueError("Choose a backup directory")
        restore(
            args.directory, args.port, args.verify_web, password_file=args.password_file
        )
    else:
        report = None
        source_config = json.loads(compose("config", "--format", "json"))
        source_rows = containers()
        source_running = [
            name for name, row in source_rows.items() if row["State"]["Running"]
        ]
        source_frontend = source_rows.get("frontend", {})
        previous_token = (
            login(source_config, "http://127.0.0.1:8080", args.password_file)
            if source_frontend.get("State", {}).get("Running")
            and args.directory is None
            else None
        )
        directory = args.directory
        previous = set()
        try:
            if directory is None:
                directory = backup(False)
            else:
                validate(directory)
                for name in ("frontend", "api"):
                    if name in source_running:
                        docker("stop", source_rows[name]["Id"])
                if (
                    "postgres" in source_running
                    and psql(
                        source_rows["postgres"]["Id"],
                        "SELECT count(*) FROM app.jobs WHERE status IN ('queued','running');",
                    )
                    != "0"
                ):
                    raise ValueError("Finish jobs before a restore trial")
                compose("stop")
            previous = set(bounded(directory).glob("smartfan-restore-*.json"))
            report = restore(
                directory, args.port, True, previous_token, args.password_file
            )
        finally:
            if report:
                compose(
                    "stop", config=Path(report["config"]), project=report["project"]
                )
            elif directory is not None:
                for path in (
                    set(bounded(directory).glob("smartfan-restore-*.json")) - previous
                ):
                    if path.name.endswith(".report.json"):
                        continue
                    project = json.loads(path.read_text(encoding="utf-8")).get(
                        "name", ""
                    )
                    if not re.fullmatch(r"smartfan-restore-[a-f0-9]{12}", project):
                        raise ValueError("Unexpected temporary restore project")
                    compose("stop", config=path, project=project)
            if not args.leave_stopped:
                resume(source_running)


if __name__ == "__main__":
    with exclusive():
        main()
