"""Portable local/CI gates using the same explicit commands."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "web-smart-fan-iot/frontend"


def run(*args: str, cwd: Path = ROOT, env: dict | None = None):
    subprocess.run(list(args), cwd=cwd, env=env, check=True)


def python(*args: str):
    run(sys.executable, *args)


def npm(*args: str):
    executable = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if executable is None:
        raise RuntimeError("Node 24/npm required for frontend checks")
    run(executable, *args, cwd=FRONTEND)


def lint():
    python("-m", "ruff", "check", "packages", "services", "infra", "tools")
    python(
        "-m",
        "ruff",
        "format",
        "--check",
        "packages",
        "services",
        "infra",
        "tools",
    )
    python(
        "-m",
        "mypy",
        "--config-file",
        "packages/smartfan_common/pyproject.toml",
        "packages/smartfan_common/src",
    )
    env = {**os.environ, "MYPYPATH": str(ROOT / "packages/smartfan_common/src")}
    run(sys.executable, "-m", "mypy", "services", "infra", env=env)
    run(
        sys.executable,
        "-m",
        "ruff",
        "check",
        "app",
        cwd=ROOT / "web-smart-fan-iot/backend",
    )
    run(sys.executable, "-m", "mypy", "app", cwd=ROOT / "web-smart-fan-iot/backend")
    for name in (
        "lint",
        "typecheck",
        "format:check",
        "contracts:types:check",
        "contracts:v2:types:check",
        "contracts:ws:types:check",
        "contracts:validators:check",
    ):
        npm("run", name)
    for script in (
        "export_contracts_v1.py",
        "export_contracts_v2.py",
        "export_ws_contracts.py",
    ):
        python("tools/" + script, "--check")


def unit():
    target = ROOT / "evidence/coverage/python-unit/.coverage"
    target.parent.mkdir(parents=True, exist_ok=True)
    run(
        sys.executable,
        "-m",
        "pytest",
        "-c",
        "pyproject.toml",
        "--cov=smartfan_common",
        "--cov=services",
        "--cov=infra",
        "--cov-config=.coveragerc",
        "--cov-report=json:evidence/coverage/python-unit.json",
        "-q",
        env={**os.environ, "COVERAGE_FILE": str(target)},
    )
    python("-m", "pytest", "web-smart-fan-iot/backend/tests", "-q")
    npm("run", "test:coverage")


if __name__ == "__main__":
    {"lint": lint, "unit": unit}[sys.argv[1]]()
