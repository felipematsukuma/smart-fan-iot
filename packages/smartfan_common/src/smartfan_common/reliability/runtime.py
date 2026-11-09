"""Bounded health state and allowlisted JSON logging; no import side effects."""

import json
import logging
import math
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str | None = None):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        fields: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service or record.name,
        }
        # Deliberately do not serialize arbitrary message/exception/request bodies.
        for name in (
            "event",
            "event_id",
            "correlation_id",
            "device_id",
            "reason_code",
            "duration_ms",
            "outcome",
        ):
            value = getattr(record, name, None)
            if value is None or isinstance(value, (str, bool, int)):
                fields[name] = value
            elif isinstance(value, float) and math.isfinite(value):
                fields[name] = value
        return json.dumps(fields, allow_nan=False)


def configure_logging(service: str) -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(logging.INFO)
    return logging.getLogger(service)


class HealthState:
    def __init__(self, max_age_seconds: float = 15):
        if not math.isfinite(max_age_seconds) or max_age_seconds <= 0:
            raise ValueError("Health heartbeat deadline must be positive")
        self.max_age_seconds = max_age_seconds
        self._tick = time.monotonic()
        self._dependencies: dict[str, bool] = {}
        self._initialized = False
        self._lock = threading.Lock()

    def tick(self, **dependencies: bool) -> None:
        with self._lock:
            self._tick = time.monotonic()
            self._dependencies = dependencies
            self._initialized = True

    def snapshot(self, readiness: bool = False) -> tuple[int, dict[str, Any]]:
        with self._lock:
            live = time.monotonic() - self._tick <= self.max_age_seconds
            ready = live and self._initialized and all(self._dependencies.values())
            healthy = ready if readiness else live
            return (200 if healthy else 503), {
                "live": live,
                "ready": ready,
                "dependencies": dict(self._dependencies),
            }


def health_server(
    state: HealthState, host: str = "0.0.0.0", port: int = 9000
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in ("/health", "/ready"):
                self.send_error(404)
                return
            code, value = state.snapshot(self.path == "/ready")
            body = json.dumps(value).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
