"""A release gate must reject missing, incomplete or failed revocation evidence."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "mutation",
    [
        "none",
        "failed",
        "missing_stack",
        "control",
        "accepted",
        "incomplete",
        "fingerprint",
        "unknown_status",
        "no_file",
    ],
)
def test_strict_history_requires_complete_positive_and_negative_controls(
    tmp_path, monkeypatch, mutation
):
    directory = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "quality_audit_scan", directory / "secret_scan.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    fingerprint = "commit:path:rule:1"
    report = {
        "stack": "legacy",
        "project": "web-smart-fan-iot",
        "passed": True,
        "ledger_findings": [fingerprint],
        "candidate_counts": {
            "POSTGRES_PASSWORD": 3,
            "INFLUXDB_TOKEN": 3,
            "INFLUXDB_PASSWORD": 3,
        },
    }
    for group in ("postgres", "influxdb", "influxdb_password"):
        report[group] = {
            "positive_control": True,
            "negative_control": True,
            "historical_accepted": 0,
            "historical_rejected": 3,
            "roles_checked": 1,
            "users_checked": 1,
        }
    second = copy.deepcopy(report)
    second.update(stack="aiot", project="smartfan-aiot")
    audit = {"passed": True, "reports": [report, second]}
    ledger = [
        {"fingerprint": fingerprint, "status": "issuer_revocation_verified_local"}
    ]
    if mutation == "failed":
        audit["passed"] = False
    elif mutation == "missing_stack":
        audit["reports"].pop()
    elif mutation == "control":
        second["postgres"]["negative_control"] = False
    elif mutation == "accepted":
        report["influxdb"]["historical_accepted"] = 1
    elif mutation == "incomplete":
        report["influxdb_password"]["historical_rejected"] = 2
    elif mutation == "fingerprint":
        second["ledger_findings"] = []
    elif mutation == "unknown_status":
        ledger[0]["status"] = "ignore"
    ledger_file, audit_file = tmp_path / "ledger.json", tmp_path / "audit.json"
    ledger_file.write_text(json.dumps(ledger), encoding="utf-8")
    if mutation != "no_file":
        audit_file.write_text(json.dumps(audit), encoding="utf-8")
    monkeypatch.setattr(module, "LEDGER", ledger_file)
    monkeypatch.setattr(module, "AUDIT", audit_file)
    monkeypatch.setattr(module, "run_scan", lambda _: [{"Fingerprint": fingerprint}])
    assert module.main("strict-history") == (0 if mutation == "none" else 1)
