"""Serial runtime acceptance with persisted coverage, then production image scans."""

import os
import shutil
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


def main():
    unit_data = ROOT / "evidence/coverage/python-unit/.coverage"
    if not unit_data.is_file():
        raise RuntimeError("Run check.py unit before collecting runtime coverage")
    for name in ("python", "python-runtime"):
        (ROOT / "evidence/coverage" / name).mkdir(parents=True, exist_ok=True)
    runtime_data = ROOT / "evidence/coverage/python-runtime"
    for previous in runtime_data.glob(".coverage*"):
        if not previous.is_file() or previous.is_symlink():
            raise RuntimeError("Unexpected runtime coverage entry")
        previous.unlink()
    run(sys.executable, "-m", "infra.prepare")
    run("docker", "compose", "build")
    run(*QA, "build", "bootstrap", "frontend")
    run(*QA, "up", "-d", "--no-build")
    try:
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
