"""Download once, pin the local model digest and warm up without cloud fallback."""

import json
import urllib.request
from pathlib import Path

MODEL = "llama3.2:3b"
LOCK = Path("/cache/.smartfan-model.json")


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
    if LOCK.exists():
        if json.loads(LOCK.read_text()) != identity:
            raise RuntimeError("Local model digest differs from approved cache lock")
    else:
        temporary = LOCK.with_suffix(".tmp")
        temporary.write_text(json.dumps(identity) + "\n")
        temporary.replace(LOCK)
    call(
        "generate",
        {
            "model": MODEL,
            "prompt": "",
            "stream": False,
            "keep_alive": "10m",
            "options": {"num_ctx": 2048, "num_thread": 4},
        },
    )
    print(
        json.dumps({"service": "ollama-init", "status": "ready", **identity}),
        flush=True,
    )


if __name__ == "__main__":
    main()
