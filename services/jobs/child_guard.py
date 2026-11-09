"""A paused/dead parent cannot leave CPU work running beyond its renewal budget."""

import json
import os
import threading
import time
from pathlib import Path


def supervise_parent(path: Path) -> None:
    parent = os.getppid()

    def watch() -> None:
        while True:
            try:
                stamp = json.loads((path / "heartbeat.json").read_bytes())[
                    "renewed_monotonic"
                ]
                alive = os.getppid() == parent and 0 <= time.monotonic() - stamp < 18
            except (OSError, ValueError, KeyError, TypeError):
                alive = False
            if not alive:
                os._exit(3)
            time.sleep(0.25)

    threading.Thread(target=watch, daemon=True, name="parent-lease-watchdog").start()
