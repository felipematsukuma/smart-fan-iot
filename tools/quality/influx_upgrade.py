"""Offline, private pre-upgrade archives plus an isolated copy, never delete volumes."""

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from tooling import ROOT, private

PYTHON = "python:3.11.18-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535"
INFLUX = "influxdb:2.9.1-alpine@sha256:cc8083573dc3969c191d1bfb768954eaf7a4c615af12e661034fd4f63c7b5570"


def docker(*args, capture=False):
    return subprocess.run(
        ["docker", *args], cwd=ROOT, check=True, text=True, capture_output=capture
    ).stdout


def prepare() -> Path:
    pending = docker(
        "compose",
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "smartfan_bootstrap",
        "-d",
        "smartfan",
        "-tAc",
        "SELECT count(*) FROM app.jobs WHERE status IN ('queued','running');",
        capture=True,
    )
    if pending.strip() != "0":
        raise RuntimeError("Finish or cancel jobs before a database backup")
    docker(
        "compose",
        "stop",
        "simulator",
        "jobs-worker",
        "control",
        "gateway",
        "writer",
        "inference",
        "api",
        "frontend",
        "influxdb",
    )
    identity = docker("compose", "ps", "-a", "-q", "influxdb", capture=True).strip()
    running = docker(
        "inspect", "--format", "{{.State.Running}}", identity, capture=True
    ).strip()
    if running != "false":
        raise RuntimeError("Offline archive requires the InfluxDB process stopped")
    mounts = json.loads(
        docker("inspect", "--format", "{{json .Mounts}}", identity, capture=True)
    )
    volumes = {
        key: next(
            row["Name"]
            for row in mounts
            if row["Destination"] == destination and row["Type"] == "volume"
        )
        for key, destination in (
            ("data", "/var/lib/influxdb2"),
            ("config", "/etc/influxdb2"),
        )
    }
    for name in volumes.values():
        labels = json.loads(
            docker(
                "volume", "inspect", "--format", "{{json .Labels}}", name, capture=True
            )
        )
        if labels.get("com.docker.compose.project") != "smartfan-aiot":
            raise RuntimeError("Unexpected source volume owner")
    suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = ROOT / "evidence/backups" / ("pre-influx-2.9.1-" + suffix)
    private(destination)
    script = "import tarfile; [(lambda t,k: (t.add('/source/'+k,arcname=k),t.close()))(tarfile.open('/backup/influx-'+k+'.tar.gz','w:gz',compresslevel=1),k) for k in ('data','config')]"
    docker(
        "run",
        "--rm",
        "--user",
        "10001:10001",
        "--network",
        "none",
        "--mount",
        "type=volume,src=" + volumes["data"] + ",dst=/source/data,readonly",
        "--mount",
        "type=volume,src=" + volumes["config"] + ",dst=/source/config,readonly",
        "--mount",
        "type=bind,src=" + str(destination) + ",dst=/backup",
        PYTHON,
        "python",
        "-c",
        script,
    )
    archives = {}
    for key in volumes:
        path = destination / ("influx-" + key + ".tar.gz")
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        archives[path.name] = {"sha256": checksum, "bytes": path.stat().st_size}
    manifest = {
        "created_at": suffix,
        "process_stopped": True,
        "source_volumes": volumes,
        "source_image": docker(
            "inspect", "--format", "{{.Config.Image}}", identity, capture=True
        ).strip(),
        "candidate": INFLUX,
        "token_hashing": False,
        "archives": archives,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(str(destination), flush=True)
    return destination


def trial(directory: Path):
    directory = directory.resolve()
    if not directory.is_relative_to((ROOT / "evidence/backups").resolve()):
        raise RuntimeError("Unexpected backup path")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for name, record in manifest["archives"].items():
        path = directory / name
        if not path.resolve().is_relative_to(directory):
            raise RuntimeError("Archive escapes private backup directory")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
                raise RuntimeError("Archive checksum mismatch")
    prefix = (
        "smartfan-influx-trial-"
        + manifest["created_at"].lower()
        + "-"
        + uuid4().hex[:6]
    )
    for key in ("data", "config"):
        docker(
            "volume",
            "create",
            "--label",
            "smartfan.purpose=upgrade-trial",
            prefix + "-" + key,
            capture=True,
        )
    script = "import tarfile,os; [(lambda t:(t.extractall('/target',filter='data'),t.close()))(tarfile.open('/backup/influx-'+k+'.tar.gz')) for k in ('data','config')]; [os.chown(os.path.join(root,name),10001,10001,follow_symlinks=False) for root,dirs,files in os.walk('/target') for name in dirs+files]; [os.chown('/target/'+k,10001,10001) for k in ('data','config')]"
    docker(
        "run",
        "--rm",
        "--user",
        "0:0",
        "--network",
        "none",
        "--mount",
        "type=volume,src=" + prefix + "-data,dst=/target/data",
        "--mount",
        "type=volume,src=" + prefix + "-config,dst=/target/config",
        "--mount",
        "type=bind,src=" + str(directory) + ",dst=/backup,readonly",
        PYTHON,
        "python",
        "-c",
        script,
    )
    docker(
        "run",
        "--rm",
        "-d",
        "--name",
        prefix,
        "--label",
        "smartfan.purpose=upgrade-trial",
        "--user",
        "10001:10001",
        "--memory",
        "1g",
        "--cpus",
        "1",
        "--network",
        "smartfan-aiot_data_net",
        "--network-alias",
        "influx-upgrade",
        "-e",
        "INFLUXD_USE_HASHED_TOKENS=false",
        "--mount",
        "type=volume,src=" + prefix + "-data,dst=/var/lib/influxdb2",
        "--mount",
        "type=volume,src=" + prefix + "-config,dst=/etc/influxdb2",
        INFLUX,
        capture=True,
    )
    manifest["trial_container"] = prefix
    manifest["trial_volumes"] = [prefix + "-data", prefix + "-config"]
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "trial_container": prefix,
                "network_alias": "influx-upgrade",
                "ports_published": False,
            }
        ),
        flush=True,
    )


def validate(directory: Path):
    directory = directory.resolve()
    if not directory.is_relative_to((ROOT / "evidence/backups").resolve()):
        raise RuntimeError("Unexpected private backup path")
    result = docker(
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "--pull",
        "never",
        "-v",
        str(ROOT / "tools/quality/influx_trial_check.py") + ":/trial_check.py:ro",
        "bootstrap",
        "python",
        "/trial_check.py",
        capture=True,
    )
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["trial_validation"] = json.loads(result)
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest["trial_validation"]))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--validate":
        validate(Path(sys.argv[2]))
    elif len(sys.argv) == 1:
        trial(prepare())
    else:
        trial(Path(sys.argv[1]))
