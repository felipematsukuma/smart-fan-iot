"""Non-root process RSS/PSS cross-check, without reading command lines or env."""

import argparse
import json
from pathlib import Path

from .common import PYTHON_IMAGE, atomic_json, containers, docker

PROBE = r"""
import json,os
totals={'rss_bytes':0,'pss_bytes':0,'swap_bytes':0,'processes':0,'permission_denied':0}
for name in os.listdir('/proc'):
    if not name.isdigit() or name==str(os.getpid()):
        continue
    try:
        with open('/proc/'+name+'/smaps_rollup') as stream:
            rows=dict((line.split(':',1)[0],int(line.split(':',1)[1].strip().split()[0])*1024) for line in stream if line.startswith(('Rss:','Pss:','Swap:')))
        totals['rss_bytes']+=rows['Rss'];totals['pss_bytes']+=rows['Pss'];totals['swap_bytes']+=rows['Swap'];totals['processes']+=1
    except (FileNotFoundError,ProcessLookupError):
        continue
    except PermissionError:
        totals['permission_denied']+=1
print(json.dumps(totals))
"""


def sample(project):
    rows = containers(project)
    observed = {}
    for service, row in rows.items():
        if not row["State"]["Running"]:
            continue
        user = row["Config"]["User"]
        if not user or user.startswith("0:") or user == "0":
            raise ValueError(
                "Resource cross-check expects non-root application services"
            )
        output = docker(
            "run",
            "--rm",
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "128m",
            "--cpus",
            "0.25",
            "--pid",
            "container:" + row["Id"],
            "--user",
            user,
            PYTHON_IMAGE,
            "python",
            "-c",
            PROBE,
        )
        observed[service] = json.loads(output)
    if not observed:
        raise ValueError("No running application services to measure")
    return {
        "project": project,
        "metric": "Sum of process smaps_rollup RSS/PSS; observer excluded, RSS conservatively counts shared mappings more than once.",
        "rss_bytes": sum(row["rss_bytes"] for row in observed.values()),
        "pss_bytes": sum(row["pss_bytes"] for row in observed.values()),
        "swap_bytes": sum(row["swap_bytes"] for row in observed.values()),
        "permission_denied": sum(row["permission_denied"] for row in observed.values()),
        "services": observed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = sample(args.project)
    if args.output:
        atomic_json(args.output, result)
    print(
        json.dumps({key: value for key, value in result.items() if key != "services"})
    )
    if result["permission_denied"]:
        raise SystemExit(1)
