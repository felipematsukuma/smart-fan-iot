"""Cache and verify the local model; warmup belongs to the fenced assistant lease."""

import hashlib
import json
import urllib.request
from pathlib import Path

from smartfan_common.local_llm import MODEL, MODEL_DIGEST

LOCK = Path("/cache/.smartfan-model-" + MODEL.replace(":", "-") + ".json")


def call(route: str, value: dict | None = None):
    request = urllib.request.Request(
        "http://ollama:11434/api/" + route,
        data=json.dumps(value).encode() if value is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.load(response)


def main() -> None:
    models = call("tags")["models"]
    match = next((m for m in models if m["name"] == MODEL), None)
    if match is None:
        print(
            json.dumps(
                {"service": "ollama-init", "status": "downloading", "model": MODEL}
            ),
            flush=True,
        )
        call("pull", {"model": MODEL, "stream": False})
        match = next(m for m in call("tags")["models"] if m["name"] == MODEL)
    identity = {"model": MODEL, "digest": match["digest"]}
    if match["digest"] != MODEL_DIGEST:
        raise RuntimeError("Downloaded model differs from approved digest")
    if LOCK.exists():
        if json.loads(LOCK.read_text()) != identity:
            raise RuntimeError("Local model digest differs from approved cache lock")
    else:
        temporary = LOCK.with_suffix(".tmp")
        temporary.write_text(json.dumps(identity) + "\n")
        temporary.replace(LOCK)
    metadata = call("show", {"model": MODEL})
    license_text = metadata.get("license", "")
    if not isinstance(license_text, str) or not license_text.strip():
        raise RuntimeError("Local model license metadata missing")
    license_record = {
        **identity,
        "license_name": "Llama 3.2 Community License",
        "license_sha256": hashlib.sha256(license_text.encode()).hexdigest(),
        "source": "https://ollama.com/library/llama3.2:1b-instruct-q4_K_M",
    }
    license_path = LOCK.with_suffix(".license.json")
    if license_path.exists() and json.loads(license_path.read_text()) != license_record:
        raise RuntimeError("Local model license differs from recorded metadata")
    temporary = license_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(license_record) + "\n")
    temporary.replace(license_path)
    # Loading/generation without the heavy lease could overlap an existing job.
    # The first authenticated chat warms the cached model under that lease.
    print(
        json.dumps({"service": "ollama-init", "status": "ready", **identity}),
        flush=True,
    )


if __name__ == "__main__":
    main()
