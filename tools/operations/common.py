"""Bounded local paths and Docker calls which never echo credential material."""

import hashlib
import json
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

from tools.quality.tooling import ROOT, private  # noqa: F401

PROJECT = "smartfan-aiot"
PYTHON_IMAGE = "python:3.11.18-slim-trixie@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535"
BACKUPS = ROOT / "evidence/backups"


@contextmanager
def exclusive():
    """Two operator commands must not stop/resume the same workspace concurrently."""
    directory = ROOT / ".tools"
    directory.mkdir(exist_ok=True)
    with (directory / "operations.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError(
                "Another local backup/restore operation is active"
            ) from None
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def docker(*args: str, data: str | None = None) -> str:
    result = subprocess.run(
        ["docker", *args], cwd=ROOT, input=data, text=True, capture_output=True
    )
    if result.returncode:
        raise RuntimeError(
            f"Docker operation failed ({result.returncode}); raw output withheld"
        )
    return result.stdout.strip()


def compose(*args: str, config: Path | None = None, project: str = PROJECT) -> str:
    return docker(
        "compose",
        "--project-directory",
        str(ROOT),
        "-f",
        str(config or ROOT / "compose.yaml"),
        "-p",
        project,
        *args,
    )


def containers(project: str = PROJECT) -> dict[str, dict]:
    names = docker(
        "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project
    ).splitlines()
    if not names:
        return {}
    rows = json.loads(docker("inspect", *names))
    result = {}
    for row in rows:
        labels = row["Config"].get("Labels", {})
        if labels.get("com.docker.compose.project") != project:
            raise RuntimeError("Container project identity differs")
        service = labels["com.docker.compose.service"]
        if labels.get("com.docker.compose.oneoff") == "True":
            continue
        result[service] = row
    return result


def bounded(directory: Path) -> Path:
    result = directory.resolve()
    if result == BACKUPS.resolve() or not result.is_relative_to(BACKUPS.resolve()):
        raise ValueError(
            "Backup must be a child of the project's private backup directory"
        )
    return result


def atomic_json(path: Path, value: dict):
    temporary = path.with_suffix(path.suffix + ".partial")
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def ready(
    project: str = PROJECT,
    services: tuple[str, ...] = ("postgres", "influxdb"),
    seconds: int = 180,
):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        rows = containers(project)
        if all(
            name in rows
            and rows[name]["State"].get("Health", {}).get("Status") == "healthy"
            for name in services
        ):
            return rows
        if any(
            name in rows and rows[name]["State"]["Status"] in ("dead", "exited")
            for name in services
        ):
            raise RuntimeError("Required service exited during readiness check")
        time.sleep(1)
    raise TimeoutError("Required services did not become healthy")
