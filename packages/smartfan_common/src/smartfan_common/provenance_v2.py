"""Canonical observed telemetry content, independent of envelope enrichment."""

import hashlib
import json

from .contracts import TelemetryData


def telemetry_digest(data: TelemetryData) -> str:
    content = data.model_dump(mode="json", exclude={"source_event_id"})
    content["quality"]["missing_fields"] = sorted(content["quality"]["missing_fields"])
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
