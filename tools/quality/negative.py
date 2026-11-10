"""Exercise real failing security/type/contract gates; restore temporary probes."""

import json
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

from conventional import valid
from tooling import ROOT, tool


def main():
    directory = ROOT / ".tools/negative"
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=directory) as temporary:
        target = Path(temporary).resolve()
        if not target.is_relative_to(directory.resolve()):
            raise RuntimeError("Unexpected negative-test directory")
        (target / "probe.env").write_text(
            "POSTGRES_PASSWORD=" + secrets.token_urlsafe(32), encoding="utf-8"
        )
        result = subprocess.run(
            [
                str(tool("gitleaks")),
                "dir",
                str(target),
                "--config=" + str(ROOT / ".gitleaks.toml"),
                "--redact=100",
                "--no-banner",
                "--log-level=error",
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode != 1:
            raise RuntimeError(
                "Secret gate failed to reject injected random credential"
            )
    frontend = ROOT / "web-smart-fan-iot/frontend"
    probe = frontend / "src/__quality_probe__.ts"
    if probe.exists() or not probe.resolve().is_relative_to(
        (frontend / "src").resolve()
    ):
        raise RuntimeError("Cannot create isolated type probe")
    try:
        probe.write_text(
            "export const qualityProbe: number = 'intentional type mismatch';\n",
            encoding="utf-8",
        )
        import shutil

        executable = shutil.which("npm.cmd") or shutil.which("npm")
        if executable is None:
            raise RuntimeError("npm unavailable")
        result = subprocess.run(
            [executable, "run", "typecheck"],
            cwd=frontend,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 or "TS2322" not in result.stdout + result.stderr:
            raise RuntimeError("Type gate did not reject isolated mismatch")
    finally:
        probe.unlink(missing_ok=True)
    sys.path.insert(0, str(ROOT / "packages/smartfan_common/src"))
    from smartfan_common.contracts_v2 import parse_event_v2

    fixture = json.loads(
        (frontend / "src/lib/ws.fixtures.json").read_text(encoding="utf-8")
    )
    snapshot = next(item["value"] for item in fixture if item["name"] == "snapshot")
    frame = next(item for item in snapshot["events"] if item["tipo"] == "frame.ready")
    frame["conteudo"]["telemetry"]["labels"] = {"health_score": 100}
    try:
        parse_event_v2(json.dumps(frame).encode())
    except ValueError:
        pass
    else:
        raise RuntimeError("Contract accepted ground truth in live telemetry")
    assert valid("feat(device): handle a registered device") and not valid(
        "unstructured title"
    )
    print(
        "Negative gates passed: injected credential, type mismatch, live labels, commit title."
    )


if __name__ == "__main__":
    main()
