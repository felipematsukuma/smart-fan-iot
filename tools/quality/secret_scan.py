"""Scan versionable files and complete Git history; never print secret material."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tooling import ROOT, tool

LEDGER = ROOT / "docs/security/history-findings.json"
# Exact reviewed placeholder file; a changed byte removes this exception.
PLACEHOLDER_SHA256 = "f417277401536587e0ef93c424cd65671c221828ca42290b9e4b542e1ac7751a"


def run_scan(mode: str) -> list[dict]:
    output = ROOT / "evidence/security" / (mode + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    command = [
        str(tool("gitleaks")),
        "git" if mode != "tree" else "dir",
        "--config=" + str(ROOT / ".gitleaks.toml"),
        "--ignore-gitleaks-allow",
        "--redact=100",
        "--no-banner",
        "--log-level=error",
        "--report-format=json",
        "--report-path=" + str(output),
    ]
    if mode == "history":
        command += ["--log-opts=--all", str(ROOT)]
    elif mode == "staged":
        command += ["--pre-commit", "--staged", str(ROOT)]
    if mode != "tree":
        result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
    else:
        base = ROOT / ".tools/scan-snapshots"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            snapshot = Path(temporary).resolve()
            if not snapshot.is_relative_to(base.resolve()):
                raise RuntimeError("Unexpected scan snapshot path")
            names = (
                subprocess.check_output(
                    [
                        "git",
                        "ls-files",
                        "--cached",
                        "--others",
                        "--exclude-standard",
                        "-z",
                    ],
                    cwd=ROOT,
                )
                .decode()
                .split("\0")
            )
            for name in names:
                source = ROOT / name
                if not name or not source.is_file():
                    continue
                if not source.resolve().is_relative_to(ROOT.resolve()):
                    raise RuntimeError("Versionable path escapes workspace")
                destination = snapshot / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            result = subprocess.run(
                [*command, str(snapshot)],
                cwd=snapshot,
                capture_output=True,
                check=False,
            )
            if output.is_file():
                normalized = json.loads(output.read_text(encoding="utf-8"))
                for row in normalized:
                    if Path(row["File"]).is_absolute():
                        row["File"] = str(Path(row["File"]).relative_to(snapshot))
                output.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    if result.returncode not in (0, 1) or not output.is_file():
        raise RuntimeError("Secret scanner failed; raw output withheld")
    rows = json.loads(output.read_text(encoding="utf-8"))
    return rows


def placeholder(row: dict, mode: str) -> bool:
    path = str(row["File"]).replace("\\", "/")
    if (
        path != "web-smart-fan-iot/.env.example"
        or row["RuleID"] != "smartfan-credential-assignment"
    ):
        return False
    if mode == "staged":
        # The working tree may differ from the index being committed.
        content = (
            subprocess.check_output(
                ["git", "show", ":web-smart-fan-iot/.env.example"], cwd=ROOT
            )
            .decode("utf-8")
            .replace("\r\n", "\n")
        )
    else:
        content = (ROOT / "web-smart-fan-iot/.env.example").read_text(encoding="utf-8")
    return hashlib.sha256(content.encode()).hexdigest() == PLACEHOLDER_SHA256


def main(mode: str) -> int:
    rows = run_scan("history" if mode == "strict-history" else mode)
    if mode in ("history", "strict-history"):
        reviewed = {
            row["fingerprint"]: row
            for row in json.loads(LEDGER.read_text(encoding="utf-8"))
        }
        new = [row for row in rows if row["Fingerprint"] not in reviewed]
        pending = [
            row
            for row in rows
            if row["Fingerprint"] in reviewed
            and reviewed[row["Fingerprint"]]["status"] == "issuer_revocation_unverified"
        ]
        print(
            json.dumps(
                {
                    "scan": mode,
                    "findings": len(rows),
                    "unreviewed": len(new),
                    "legacy_pending": len(pending),
                    "clean_history": not new and not pending,
                }
            )
        )
        return int(bool(new or (pending and mode == "strict-history")))
    findings = [row for row in rows if not placeholder(row, mode)]
    print(
        json.dumps(
            {
                "scan": mode,
                "findings": len(findings),
                "reviewed_placeholders": len(rows) - len(findings),
            }
        )
    )
    for row in findings:
        print(
            json.dumps(
                {
                    "rule": row["RuleID"],
                    "file": Path(row["File"]).name,
                    "line": row["StartLine"],
                }
            )
        )
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
