"""Provision a bucket-scoped token without exposing setup credentials to runtimes."""

import json
import os
import urllib.request
from pathlib import Path


def provision_token(
    headers: dict[str, str],
    org_id: str,
    bucket_permissions: list[tuple[str, str]],
    directory: Path,
    description: str,
) -> None:
    def request(path, body=None):
        req = urllib.request.Request(
            "http://influxdb:8086/api/v2/" + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={**headers, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)

    permissions = [
        {
            "action": action,
            "resource": {"type": "buckets", "id": bucket_id, "orgID": org_id},
        }
        for bucket_id, action in bucket_permissions
    ]
    candidates = [
        item
        for item in request("authorizations?orgID=" + org_id)["authorizations"]
        if item.get("description") == description
    ]
    if len(candidates) > 1:
        raise RuntimeError(
            "Ambiguous writer token; explicit credential reconciliation required"
        )
    authorization = (
        candidates[0]
        if candidates
        else request(
            "authorizations",
            {
                "orgID": org_id,
                "description": description,
                "permissions": permissions,
                "status": "active",
            },
        )
    )
    actual = authorization["permissions"]
    if (
        len(actual) != len(permissions)
        or {
            (item["resource"].get("id"), item["action"], item["resource"]["type"])
            for item in actual
        }
        != {(bucket, action, "buckets") for bucket, action in bucket_permissions}
        or authorization["status"] != "active"
    ):
        raise RuntimeError("Writer token scope is invalid")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "token"
    token = authorization["token"]
    if path.exists():
        if path.read_text().strip() != token:
            raise RuntimeError("Writer token differs from provisioned authorization")
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        with os.fdopen(fd, "w") as stream:
            stream.write(token + "\n")


def provision_writer(
    headers: dict[str, str], org_id: str, bucket_id: str, directory: Path
) -> None:
    provision_token(
        headers, org_id, [(bucket_id, "write")], directory, "smartfan-writer-live-v1"
    )
