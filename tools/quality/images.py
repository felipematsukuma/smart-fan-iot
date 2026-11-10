"""Scan all selected runtime images; any critical finding or scanner error fails."""

import hashlib
import json
import subprocess

from tooling import ROOT, tool


def main() -> int:
    images = sorted(
        set(
            subprocess.check_output(
                ["docker", "compose", "config", "--images"], cwd=ROOT, text=True
            ).splitlines()
        )
    )
    directory = ROOT / "evidence/security/images"
    directory.mkdir(parents=True, exist_ok=True)
    results = []
    for reference in images:
        path = directory / (
            hashlib.sha256(reference.encode()).hexdigest()[:12] + ".json"
        )
        path.unlink(missing_ok=True)
        result = subprocess.run(
            [
                str(tool("trivy")),
                "image",
                "--quiet",
                "--scanners",
                "vuln",
                "--severity",
                "CRITICAL",
                "--exit-code",
                "1",
                "--format",
                "json",
                "--output",
                str(path),
                reference,
            ],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if result.returncode not in (0, 1) or not path.is_file():
            raise RuntimeError("Image scanner failed for selected image")
        report = json.loads(path.read_text(encoding="utf-8"))
        if not report.get("Metadata", {}).get("ImageID"):
            raise RuntimeError("Image scanner omitted the inspected image identity")
        findings = [
            {
                "id": item["VulnerabilityID"],
                "package": item["PkgName"],
                "installed": item["InstalledVersion"],
                "fixed": item.get("FixedVersion"),
            }
            for section in report.get("Results", [])
            for item in section.get("Vulnerabilities") or []
        ]
        record = {
            "image": reference,
            "image_id": report.get("Metadata", {}).get("ImageID"),
            "critical": findings,
            "scanner_exit": result.returncode,
        }
        results.append(record)
        print(json.dumps(record), flush=True)
    (directory / "summary.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    return int(any(row["critical"] or row["scanner_exit"] for row in results))


if __name__ == "__main__":
    raise SystemExit(main())
