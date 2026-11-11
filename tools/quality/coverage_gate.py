"""Explicit application scopes: global >=70%, business/contract/ML branches >=80%."""

import json
from datetime import UTC, datetime

from tooling import ROOT

COMMON = {
    "contracts": {
        "contracts.py",
        "contracts_v2.py",
        "ws_protocol.py",
        "routing.py",
        "routing_v2.py",
    },
    "domain": {
        "control.py",
        "device_registry.py",
        "energy_v2.py",
        "lab_config.py",
        "predictive.py",
        "provenance_v2.py",
        "training_config.py",
    },
    "ml": {"features.py", "features_v2.py", "ml_pipeline.py", "model_policy.py"},
}
ML_SERVICES = {
    "services/jobs/batch_features.py",
    "services/jobs/generate.py",
    "services/jobs/train.py",
    "services/inference/models.py",
    "services/inference/window.py",
    "services/inference/worker.py",
}
FRONTEND_CORE = {
    "auth.ts",
    "access.ts",
    "live-store.ts",
    "insights.ts",
    "assistant-stream.ts",
    "assistant-markdown.ts",
    "scene/model.ts",
}


def ratio(covered: int, total: int) -> float:
    return 100 * covered / total if total else 100.0


def main() -> int:
    directory = ROOT / "evidence/coverage"
    python = json.loads((directory / "python.json").read_text(encoding="utf-8"))
    frontend = json.loads((directory / "frontend.json").read_text(encoding="utf-8"))
    groups: dict[str, list] = {name: [] for name in COMMON}
    for path, row in python["files"].items():
        path = path.replace("\\", "/")
        name = path.rsplit("/", 1)[-1]
        for group, names in COMMON.items():
            if "smartfan_common/" in path and name in names:
                groups[group].append(row["summary"])
        if path.startswith(
            ("services/control/", "services/simulator/")
        ) and name not in ("main.py", "__init__.py"):
            groups["domain"].append(row["summary"])
        if path in ML_SERVICES:
            groups["ml"].append(row["summary"])
    results = {
        "python_global": {"percent": python["totals"]["percent_covered"], "minimum": 70}
    }
    for group, rows in groups.items():
        if not rows:
            raise RuntimeError("Required application coverage scope missing")
        results["python_" + group + "_branches"] = {
            "percent": ratio(
                sum(row["covered_branches"] for row in rows),
                sum(row["num_branches"] for row in rows),
            ),
            "minimum": 80,
        }
    lines: dict[tuple[str, int], bool] = {}
    core_covered = core_total = 0
    for path, row in frontend.items():
        normalized = path.replace("\\", "/")
        core = "/src/lib/" in normalized or any(
            normalized.endswith("/src/aiot/" + name) for name in FRONTEND_CORE
        )
        for identity, location in row["statementMap"].items():
            key = path, location["start"]["line"]
            lines[key] = lines.get(key, False) or row["s"][identity] > 0
        if core:
            for values in row["b"].values():
                core_covered += sum(value > 0 for value in values)
                core_total += len(values)
    if not lines or not core_total:
        raise RuntimeError("Frontend application coverage missing")
    results["frontend_global_lines"] = {
        "percent": ratio(sum(lines.values()), len(lines)),
        "minimum": 70,
    }
    results["frontend_business_branches"] = {
        "percent": ratio(core_covered, core_total),
        "minimum": 80,
    }
    for record in results.values():
        record["passed"] = record["percent"] >= record["minimum"]
        record["percent"] = round(record["percent"], 2)
    summary = {
        "measured_at": datetime.now(UTC).isoformat(),
        "scopes": results,
        "passed": all(record["passed"] for record in results.values()),
    }
    (directory / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return int(not summary["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
