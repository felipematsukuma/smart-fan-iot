"""Fetch only pinned release binaries and verify their published SHA-256."""

import csv
import hashlib
import io
import os
import platform
import subprocess
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def private(directory: Path):
    """A new operator-owned directory, without inherited Windows group access."""
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    if os.name == "nt":
        actor = next(
            csv.reader(
                subprocess.check_output(
                    ["whoami", "/user", "/fo", "csv", "/nh"], text=True
                ).splitlines()
            )
        )[1]
        subprocess.run(
            [
                "icacls",
                str(directory),
                "/inheritance:r",
                "/grant:r",
                "*" + actor + ":(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
            ],
            check=True,
            capture_output=True,
        )


RELEASES = {
    "gitleaks": {
        "version": "8.30.1",
        "repo": "gitleaks/gitleaks",
        "windows": (
            "gitleaks_8.30.1_windows_x64.zip",
            "d29144deff3a68aa93ced33dddf84b7fdc26070add4aa0f4513094c8332afc4e",
        ),
        "linux": (
            "gitleaks_8.30.1_linux_x64.tar.gz",
            "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb",
        ),
    },
    "trivy": {
        "version": "0.76.2",
        "repo": "aquasecurity/trivy",
        "windows": (
            "trivy_0.76.2_windows-64bit.zip",
            "691f737a7e5566a673c3a74dab9160552ec32101e953b659e5c77443d16dddb6",
        ),
        "linux": (
            "trivy_0.76.2_Linux-64bit.tar.gz",
            "bc0fc726e017b8927a62b2d3531d7a84ee01769daf5c99ed866dced54089fdbf",
        ),
    },
}


def tool(name: str) -> Path:
    if platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Pinned tooling supports x86_64 Windows/Linux only")
    system = platform.system().lower()
    if system not in ("windows", "linux"):
        raise RuntimeError("Pinned tooling supports Windows/Linux only")
    release = RELEASES[name]
    filename, expected = release[system]
    executable = name + (".exe" if system == "windows" else "")
    destination = ROOT / ".tools" / name / release["version"] / executable
    marker = destination.with_suffix(".sha256")
    if (
        destination.is_file()
        and marker.is_file()
        and hashlib.sha256(destination.read_bytes()).hexdigest()
        == marker.read_text().strip()
    ):
        return destination
    url = f"https://github.com/{release['repo']}/releases/download/v{release['version']}/{filename}"
    with urllib.request.urlopen(url, timeout=120) as response:
        archive = response.read(150 * 1024**2)
    if hashlib.sha256(archive).hexdigest() != expected:
        raise RuntimeError("Tool release checksum mismatch")
    if filename.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            raw = package.read(executable)
    else:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
            member = package.getmember(executable)
            stream = package.extractfile(member)
            if stream is None:
                raise RuntimeError("Tool executable missing")
            raw = stream.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial")
    temporary.write_bytes(raw)
    os.replace(temporary, destination)
    destination.chmod(0o755)
    marker.write_text(hashlib.sha256(raw).hexdigest() + "\n")
    return destination


if __name__ == "__main__":
    import sys

    print(tool(sys.argv[1]))
