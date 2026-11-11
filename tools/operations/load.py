"""Real multi-device MQTT load, restricted to an isolated restored project."""

import argparse
import copy
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
from websockets.sync.client import connect

from infra.prepare import mqtt_password_hash

from .backup import login, mount_source, source_credentials
from .common import (
    PYTHON_IMAGE,
    ROOT,
    atomic_json,
    compose,
    containers,
    docker,
    exclusive,
    private,
    ready,
)


def utc():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def percentile(values, fraction=0.95):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)] if ordered else None


def scoped(config: dict):
    project = config.get("name", "")
    if not re.fullmatch(r"smartfan-restore-[a-f0-9]{12}", project):
        raise ValueError("Load is allowed only in a restored test project")
    if any(row["State"]["Running"] for row in containers().values()):
        raise ValueError("Stop the original project before using the test copy")
    return project


def api(client, method, path, token, body=None):
    response = client.request(
        method, path, headers={"Authorization": "Bearer " + token}, json=body
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Acceptance HTTP request failed ({response.status_code})")
    return response.json() if response.status_code != 204 else None


def provision(base: Path, count: int, interval: float):
    config = json.loads(base.read_text(encoding="utf-8"))
    project = scoped(config)
    identity = uuid4().hex
    directory = ROOT / "evidence/acceptance" / identity
    private(directory)
    url = "http://127.0.0.1:" + str(
        config["services"]["frontend"]["ports"][0]["published"]
    )
    original_passwords = mount_source(
        config, "mosquitto", "/run/secrets/mosquitto-passwords"
    ).read_text()
    original_acl = mount_source(
        config, "mosquitto", "/mosquitto/config/acl"
    ).read_text()
    password_lines = []
    acl_lines = []
    devices = []
    services = []
    prototype = copy.deepcopy(config["services"]["simulator"])
    config["services"]["simulator"]["profiles"] = ["original-device"]
    current_config = json.loads(compose("config", "--format", "json"))
    current = current_config["services"]["bootstrap"]["image"]
    config["services"]["frontend"]["image"] = current_config["services"]["frontend"][
        "image"
    ]
    for index in range(1, count + 1):
        device = "t" + identity[:6] + "_" + str(index)
        service = f"load-{index:02d}"
        devices.append(device)
        services.append(service)
        credential = secrets.token_hex(32)
        password = directory / (device + ".credential")
        password.write_text(credential + "\n", encoding="utf-8")
        password.chmod(0o444)
        password_lines.append(
            "simulator_" + device + ":" + mqtt_password_hash(credential)
        )
        acl_lines += [
            "user simulator_" + device,
            *[
                "topic write devices/" + device + "/" + topic
                for topic in ("telemetry", "state", "acks", "availability")
            ],
            *[
                "topic read devices/" + device + "/" + topic
                for topic in ("commands", "receipts")
            ],
            "",
        ]
        logical = f"load_{index:02d}_spool"
        volume = project + "_" + identity[:8] + "_" + logical
        docker(
            "volume",
            "create",
            "--label",
            "com.docker.compose.project=" + project,
            "--label",
            "com.docker.compose.volume=" + logical,
            "--label",
            "smartfan.acceptance.run=" + identity,
            volume,
        )
        docker(
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--user",
            "0:0",
            "--cap-drop",
            "ALL",
            "--cap-add",
            "CHOWN",
            "--mount",
            "type=volume,src=" + volume + ",dst=/target",
            PYTHON_IMAGE,
            "python",
            "-c",
            "import os;os.chown('/target',10001,10001)",
        )
        config["volumes"][logical] = {"external": True, "name": volume}
        actor = copy.deepcopy(prototype)
        actor["image"] = current
        actor["environment"] = {
            **actor.get("environment", {}),
            "SIM_DEVICE_ID": device,
            "SIM_ZONE": "quarto",
            "SIM_INTERVAL_SECONDS": str(interval),
        }
        actor["volumes"] = [
            {"type": "volume", "source": logical, "target": "/data"},
            {
                "type": "bind",
                "source": str(password),
                "target": "/run/secrets/mqtt_password",
                "read_only": True,
            },
        ]
        config["services"][service] = actor
    passwords = directory / "mosquitto-passwords"
    acl = directory / "mosquitto-acl"
    passwords.write_text(
        original_passwords.rstrip() + "\n" + "\n".join(password_lines) + "\n",
        encoding="utf-8",
    )
    acl.write_text(
        original_acl.rstrip() + "\n\n" + "\n".join(acl_lines), encoding="utf-8"
    )
    for item in config["services"]["mosquitto"]["volumes"]:
        if item["target"] == "/run/secrets/mosquitto-passwords":
            item["source"] = str(passwords)
        if item["target"] == "/mosquitto/config/acl":
            item["source"] = str(acl)
    path = directory / "compose.json"
    atomic_json(path, config)
    # Register before starting new publishers. Original snapshot bind files remain immutable.
    compose("up", "-d", "--no-build", "api", "frontend", config=base, project=project)
    ready(project, services=("api", "frontend"))
    token = login(config, url)
    with httpx.Client(base_url=url, timeout=5, trust_env=False) as client:
        for item in api(client, "GET", "/api/v1/devices", token)["items"]:
            if item["enabled"]:
                api(
                    client,
                    "PATCH",
                    "/api/v1/devices/" + item["id"],
                    token,
                    {"expected_revision": item["revision"], "enabled": False},
                )
        for index, device in enumerate(devices, 1):
            api(
                client,
                "POST",
                "/api/v1/devices",
                token,
                {
                    "id": device,
                    "name": "Ensaio de carga " + str(index),
                    "zone": "quarto",
                },
            )
        api(client, "POST", "/api/v1/auth/logout", token, {})
    compose("up", "-d", "--no-build", config=path, project=project)
    ready(
        project,
        services=(
            "api",
            "frontend",
            "gateway",
            "writer",
            "inference",
            "control",
            *services,
        ),
    )
    state = {
        "run_id": identity,
        "project": project,
        "config": str(path),
        "url": url,
        "devices": devices,
        "services": services,
        "interval_seconds": interval,
        "directory": str(directory),
    }
    atomic_json(directory / "state.json", state)
    return state, config


def journal(config, project, devices, start, stop):
    payload = {
        **source_credentials(config),
        "devices": devices,
        "start": start,
        "stop": stop,
    }
    image = config["services"]["bootstrap"]["image"]
    output = docker(
        "run",
        "--rm",
        "--pull",
        "never",
        "-i",
        "--read-only",
        "--tmpfs",
        "/tmp",
        "--memory",
        "384m",
        "--cpus",
        "1",
        "--network",
        project + "_data_net",
        "--mount",
        "type=bind,src="
        + str(Path(__file__).resolve().parent)
        + ",dst=/operations,readonly",
        "-w",
        "/",
        image,
        "python",
        "-m",
        "operations.ingestion_probe",
        data=json.dumps(payload),
    )
    return json.loads(output)


def collect(url, token, devices, stop, output, errors):
    try:
        with httpx.Client(base_url=url, timeout=5, trust_env=False) as client:
            response = client.post(
                "/api/v1/auth/ws-ticket",
                headers={"Authorization": "Bearer " + token, "Origin": url},
                json={"devices": devices},
            )
            response.raise_for_status()
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
                        "ticket": response.json()["ticket"],
                        "devices": devices,
                    }
                )
            )
            while not stop.is_set():
                try:
                    event = json.loads(stream.recv(timeout=1))
                except TimeoutError:
                    continue
                if event.get("type") == "ping":
                    stream.send(json.dumps({"type": "pong", "id": event["id"]}))
                if event.get("tipo") == "frame.ready":
                    now = datetime.now(UTC)
                    output.append(
                        {
                            "device": event["dispositivo"],
                            "source_ms": (
                                now - datetime.fromisoformat(event["timestamp"])
                            ).total_seconds()
                            * 1000,
                            "gateway_ms": (
                                now
                                - datetime.fromisoformat(
                                    event["metadata"]["observed_at"]
                                )
                            ).total_seconds()
                            * 1000,
                            "status": event["conteudo"]["insight"]["status"],
                            "model_version": event["conteudo"]["insight"][
                                "model_version"
                            ],
                        }
                    )
    except Exception as error:
        errors.append(type(error).__name__)


def api_worker(url, token, device, stop, output):
    deadline = time.monotonic() + 60
    paths = (
        "/api/v1/devices",
        "/api/v1/devices/" + device,
        "/api/v1/devices/" + device + "/control",
        "/api/v1/devices/" + device + "/metrics?hours=24",
    )
    with httpx.Client(base_url=url, timeout=5, trust_env=False) as client:
        index = 0
        while not stop.is_set() and time.monotonic() < deadline:
            path = paths[index % len(paths)]
            began = time.monotonic()
            try:
                response = client.get(
                    path, headers={"Authorization": "Bearer " + token}
                )
                status = response.status_code
            except httpx.HTTPError:
                status = 0
            output.append(
                {
                    "route": path,
                    "status": status,
                    "ms": (time.monotonic() - began) * 1000,
                }
            )
            index += 1
            stop.wait(0.5)


def stats_worker(project, stop, output, errors):
    ids = [row["Id"] for row in containers(project).values() if row["State"]["Running"]]
    units = {"B": 1, "kB": 1000, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
    while not stop.is_set():
        began = time.monotonic()
        try:
            raw = docker("stats", "--no-stream", "--format", "{{json .}}", *ids)
            rows = [json.loads(line) for line in raw.splitlines()]
            total = 0
            cpu = 0.0
            for row in rows:
                match = re.fullmatch(
                    r"([\d.]+)\s*(B|kB|KiB|MiB|GiB)",
                    row["MemUsage"].split("/")[0].strip(),
                )
                if match is None:
                    raise ValueError("Unknown Docker memory unit")
                total += float(match[1]) * units[match[2]]
                cpu += float(row["CPUPerc"].removesuffix("%"))
            output.append(
                {
                    "at": utc(),
                    "working_set_bytes": round(total),
                    "cpu_percent": round(cpu, 3),
                    "containers": rows,
                }
            )
        except (RuntimeError, ValueError, KeyError):
            errors.append("docker_stats_failed")
        stop.wait(max(0, 1 - (time.monotonic() - began)))


def browser_probe(state, config):
    executable = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if executable is None:
        raise RuntimeError("npm is required for real screen latency")
    directory = Path(state["directory"])
    log = (directory / "browser.log").open("w", encoding="utf-8")
    environment = {
        **os.environ,
        "AIOT_PERF_URL": state["url"],
        "AIOT_PERF_DEVICE": state["devices"][0],
        "AIOT_PERF_PASSWORD_FILE": str(
            mount_source(config, "bootstrap", "/run/secrets/initial_operator_password")
        ),
        "AIOT_PERF_SECONDS": "60",
        "AIOT_PERF_REPORT": str(directory / "browser.report.json"),
    }
    process = subprocess.Popen(
        [executable, "run", "test:e2e", "--", "e2e/performance.spec.ts"],
        cwd=ROOT / "web-smart-fan-iot/frontend",
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    return process, log


def run(base, seconds, count, interval, browser=False):
    state, config = provision(base, count, interval)
    project = state["project"]
    path = Path(state["config"])
    directory = Path(state["directory"])
    token = login(config, state["url"])
    frames, errors = [], []
    stop = threading.Event()
    collector = threading.Thread(
        target=collect,
        args=(state["url"], token, state["devices"], stop, frames, errors),
        daemon=True,
    )
    start = utc()
    began = time.monotonic()
    collector.start()
    queue_samples = []
    resource_samples = []
    resource_errors = []
    resource_collector = threading.Thread(
        target=stats_worker,
        args=(project, stop, resource_samples, resource_errors),
        daemon=True,
    )
    resource_collector.start()
    api_samples = []
    api_threads = []
    browser_process = None
    browser_log = None
    try:
        with httpx.Client(base_url=state["url"], timeout=5, trust_env=False) as client:
            while time.monotonic() - began < seconds:
                if (
                    browser
                    and time.monotonic() - began >= 300
                    and browser_process is None
                ):
                    browser_process, browser_log = browser_probe(state, config)
                    for _ in range(10):
                        worker = threading.Thread(
                            target=api_worker,
                            args=(
                                state["url"],
                                token,
                                state["devices"][0],
                                stop,
                                api_samples,
                            ),
                            daemon=True,
                        )
                        api_threads.append(worker)
                        worker.start()
                snapshot = api(client, "GET", "/api/v1/messaging", token)
                queue_samples.append(snapshot)
                print(
                    json.dumps(
                        {
                            "phase": "load",
                            "elapsed_seconds": round(time.monotonic() - began, 1),
                            "live_frames": len(frames),
                            "ready_messages": sum(
                                row["messages_ready"]
                                for row in snapshot["queues"]
                                if row["name"] != "q.dlq"
                            ),
                        }
                    ),
                    flush=True,
                )
                stop.wait(min(10, max(0, seconds - (time.monotonic() - began))))
        end = utc()
        stop.set()
        collector.join(timeout=3)
        resource_collector.join(timeout=4)
        compose("stop", *state["services"], config=path, project=project)
        deadline = time.monotonic() + 120
        final = None
        with httpx.Client(base_url=state["url"], timeout=5, trust_env=False) as client:
            while time.monotonic() < deadline:
                final = api(client, "GET", "/api/v1/messaging", token)
                if not any(
                    row["messages_ready"] + row["messages_unacknowledged"]
                    for row in final["queues"]
                    if row["name"] != "q.dlq"
                ):
                    candidate = journal(config, project, state["devices"], start, end)
                    accepted_ids = {row[0] for row in candidate["source"]}
                    completed_ids = {row[0] for row in candidate["source"] if row[3]}
                    if candidate["inbox_pending"] == candidate[
                        "outbox_pending"
                    ] == 0 and accepted_ids == completed_ids == set(
                        candidate["influx_ids"]
                    ):
                        break
                time.sleep(1)
            else:
                raise RuntimeError("Queues did not drain within 120 seconds")
        observed = journal(config, project, state["devices"], start, end)
        accepted = {row[0] for row in observed["source"]}
        completed = {row[0] for row in observed["source"] if row[3]}
        persisted = observed["influx_ids"]
        start_time = datetime.fromisoformat(start)
        end_time = datetime.fromisoformat(end)
        in_window = [
            row
            for row in observed["source"]
            if start_time <= datetime.fromisoformat(row[2]) < end_time
        ]
        duration = (
            datetime.fromisoformat(end) - datetime.fromisoformat(start)
        ).total_seconds()
        rate = len(in_window) / duration
        report = {
            "run_id": state["run_id"],
            "project": project,
            "started_at": start,
            "stopped_at": end,
            "seconds": round(duration, 3),
            "devices": count,
            "interval_seconds": interval,
            "gateway_accepted_in_window": len(in_window),
            "accepted_per_second": round(rate, 3),
            "accepted_all_run": len(accepted),
            "writer_completed": len(completed),
            "influx_unique": len(set(persisted)),
            "influx_records": len(persisted),
            "no_accepted_loss": accepted == completed == set(persisted),
            "no_duplicate_points": len(persisted) == len(set(persisted)),
            "final_backlog": sum(
                row["messages_ready"] + row["messages_unacknowledged"]
                for row in final["queues"]
                if row["name"] != "q.dlq"
            ),
            "amqp_unique_by_owner_and_prefix": observed["amqp"],
            "host_ws_frames": len(frames),
            "host_ws_source_p95_ms": percentile([row["source_ms"] for row in frames]),
            "host_ws_gateway_p95_ms": percentile([row["gateway_ms"] for row in frames]),
            "ws_errors": errors,
            "valid_prediction_frames": sum(row["status"] == "valid" for row in frames),
            "model_versions": sorted(
                {row["model_version"] for row in frames if row["model_version"]}
            ),
            "screen_latency_measured": False,
            "sql_inbox_pending": observed["inbox_pending"],
            "sql_outbox_pending": observed["outbox_pending"],
            "peak_docker_working_set_bytes": max(
                (sample["working_set_bytes"] for sample in resource_samples),
                default=None,
            ),
            "memory_metric": "Docker working set per approved docker-stats method; not a sum of per-process RSS.",
            "resource_errors": resource_errors,
        }
        if browser_process is not None:
            browser_process.wait(timeout=10)
            browser_log.close()
            if browser_process.returncode:
                raise RuntimeError(
                    "Actual browser latency test failed; see private browser log"
                )
            screen = json.loads((directory / "browser.report.json").read_text())
            report.update(screen_latency_measured=True, screen=screen)
        grouped = {
            path: [row for row in api_samples if row["route"] == path]
            for path in sorted({row["route"] for row in api_samples})
        }
        report["api_routes"] = {
            path: {
                "requests": len(rows),
                "errors": sum(row["status"] != 200 for row in rows),
                "p95_ms": percentile([row["ms"] for row in rows]),
                "target_ms": 1000 if "/metrics?" in path else 300,
            }
            for path, rows in grouped.items()
        }
        report["api_ten_concurrent_clients"] = len(api_threads) == 10
        report["passed"] = (
            report["no_accepted_loss"]
            and report["no_duplicate_points"]
            and report["final_backlog"] == 0
            and not errors
            and len(frames) >= count * seconds / 2
            and report["sql_inbox_pending"] == report["sql_outbox_pending"] == 0
            and not resource_errors
            and (rate >= 20 if seconds >= 600 else rate > 0)
            and (
                sum(row["status"] == "valid" for row in frames) >= count * 10
                if seconds >= 600
                else True
            )
        )
        if browser:
            report["passed"] = (
                report["passed"]
                and report["screen_latency_measured"]
                and report["api_ten_concurrent_clients"]
                and all(
                    row["errors"] == 0 and row["p95_ms"] <= row["target_ms"]
                    for row in report["api_routes"].values()
                )
            )
        atomic_json(directory / "load.report.json", report)
        atomic_json(directory / "queue.samples.json", {"samples": queue_samples})
        atomic_json(directory / "resources.samples.json", {"samples": resource_samples})
        atomic_json(directory / "api.samples.json", {"samples": api_samples})
        print(json.dumps({"phase": "load_complete", **report}), flush=True)
        if not report["passed"]:
            raise RuntimeError("Actual multi-device load acceptance failed")
    finally:
        stop.set()
        collector.join(timeout=3)
        resource_collector.join(timeout=4)
        for worker in api_threads:
            worker.join(timeout=5)
        if browser_process is not None and browser_process.poll() is None:
            browser_process.terminate()
            browser_process.wait(timeout=10)
        if browser_log is not None and not browser_log.closed:
            browser_log.close()
        compose("stop", config=path, project=project)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--devices", type=int, default=10)
    parser.add_argument("--interval", type=float, default=0.4)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    if (
        not 20 <= args.seconds <= 600
        or not 1 <= args.devices <= 10
        or not 0.2 <= args.interval <= 2
    ):
        raise ValueError("Invalid bounded acceptance workload")
    if args.browser and args.seconds != 600:
        raise ValueError(
            "Screen/API concurrency acceptance requires the full ten-minute load"
        )
    run(args.config, args.seconds, args.devices, args.interval, args.browser)


if __name__ == "__main__":
    with exclusive():
        main()
