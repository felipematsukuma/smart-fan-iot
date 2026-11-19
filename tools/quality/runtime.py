"""Serial runtime acceptance with persisted coverage, then production image scans."""

import os
import shutil
import subprocess
import sys

from check import FRONTEND, ROOT, run

QA = ["docker", "compose", "-f", "compose.yaml", "-f", "infra/compose.coverage.yaml"]
TESTS = (
    "reliability",
    "gateway",
    "writer",
    "api",
    "realtime",
    "devices",
    "control",
    "messaging",
    "lab",
    "models",
    "inference",
    "insights",
    "assistant",
)


def prepare_coverage_directory(directory):
    if os.name == "nt":
        return  # Docker Desktop supplies the bind-mount permissions.
    if (
        directory.is_symlink()
        or directory.resolve().parent != (ROOT / "evidence/coverage").resolve()
    ):
        raise RuntimeError("Unexpected coverage directory")
    # Only this test artifact directory: app UID writes; runner GID reads and
    # removes old files. No world-write and no production volume is mounted.
    run(
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--user",
        "0:0",
        "--mount",
        f"type=bind,source={directory.resolve()},target=/coverage",
        "--entrypoint",
        "python",
        "smartfan-python-qa:0.14.0",
        "-c",
        f"import os; os.chown('/coverage',10001,{os.getgid()}); os.chmod('/coverage',0o2770)",
    )


def bootstrap_diagnostic():
    result = subprocess.run(
        [*QA, "logs", "--no-color", "--tail", "100", "bootstrap"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    output = result.stdout + result.stderr
    for path in (ROOT / "secrets").iterdir():
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                output = output.replace(value, "[REDACTED]")
    print(output, flush=True)


def main():
    unit_data = ROOT / "evidence/coverage/python-unit/.coverage"
    if not unit_data.is_file():
        raise RuntimeError("Run check.py unit before collecting runtime coverage")
    for name in ("python", "python-runtime"):
        (ROOT / "evidence/coverage" / name).mkdir(parents=True, exist_ok=True)
    runtime_data = ROOT / "evidence/coverage/python-runtime"
    run(sys.executable, "-m", "infra.prepare")
    run("docker", "compose", "build")
    run(*QA, "build", "bootstrap", "frontend")
    prepare_coverage_directory(runtime_data)
    for previous in runtime_data.glob(".coverage*"):
        if not previous.is_file() or previous.is_symlink():
            raise RuntimeError("Unexpected runtime coverage entry")
        previous.unlink()
    try:
        try:
            run(*QA, "up", "-d", "--no-build")
        except subprocess.CalledProcessError:
            bootstrap_diagnostic()
            raise
        run(
            *QA,
            "run",
            "--rm",
            "--no-deps",
            "--pull",
            "never",
            "bootstrap",
            "python",
            "-m",
            "coverage",
            "run",
            "-m",
            "pytest",
            *["/tests/test_" + name + "_integration.py" for name in TESTS],
            "/tests/test_realtime_runtime.py",
            "-q",
            "-p",
            "no:cacheprovider",
            "--tb=short",
        )
        # Serial: model CPU work must not compete with scans or another test suite.
        executable = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if executable is None:
            raise RuntimeError("npm missing")
        run(
            executable,
            "run",
            "test:e2e",
            cwd=FRONTEND,
            env={**os.environ, "AIOT_COVERAGE": "1"},
        )
        run("node", "scripts/coverage-merge.mjs", cwd=FRONTEND)
    finally:
        # SIGTERM/graceful exit writes coverage; volumes are preserved.
        run(*QA, "stop")
    data = ROOT / "evidence/coverage/python/.coverage"
    environment = {**os.environ, "COVERAGE_FILE": str(data)}
    run(
        sys.executable,
        "-m",
        "coverage",
        "combine",
        "--keep",
        str(unit_data),
        str(runtime_data),
        env=environment,
    )
    run(
        sys.executable,
        "-m",
        "coverage",
        "json",
        "-o",
        "evidence/coverage/python.json",
        env=environment,
    )
    run(sys.executable, "tools/quality/coverage_gate.py")
    # Runtime images are scanned after all model/training work has stopped.
    run(sys.executable, "tools/quality/images.py")


if __name__ == "__main__":
    main()
