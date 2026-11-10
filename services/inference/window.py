"""Past-only recovery uses original Influx timestamps, never a replay receipt clock."""

from datetime import datetime, timedelta

from smartfan_common.contracts_v2 import TelemetryPersistedV2
from smartfan_common.features import SENSORS, FeatureSample, FeatureWindow
from smartfan_common.influx_v2 import InfluxHTTP


class Windows:
    def __init__(self, influx: InfluxHTTP | None):
        self.influx = influx
        self.window = FeatureWindow()
        self.restored: set[tuple[str, str]] = set()

    def push(self, event: TelemetryPersistedV2):
        key = (event.dispositivo, event.metadata.boot_id)
        at = datetime.fromisoformat(event.timestamp)
        if key not in self.restored:
            self.window.forget(event.dispositivo)
            if self.influx is not None:
                try:
                    rows = self.influx.query(
                        self.influx.history_query(
                            event.dispositivo, at - timedelta(seconds=60), at, 1000
                        )
                    )
                    for row in rows:
                        if row.get("boot_id") != event.metadata.boot_id:
                            continue
                        stamp = datetime.fromisoformat(row["_time"]).timestamp()
                        if not at.timestamp() - 60 <= stamp < at.timestamp():
                            continue
                        if row.get("compressor_on") not in ("true", "false"):
                            continue
                        self.window.push_sample(
                            FeatureSample(
                                event.dispositivo,
                                event.metadata.boot_id,
                                int(row["sequence"]),
                                stamp,
                                row["compressor_on"] == "true",
                                tuple(
                                    float(row[field]) if row.get(field) else None
                                    for field in SENSORS
                                ),
                            )
                        )
                except (OSError, ValueError, KeyError):
                    # Current samples still warm the same bounded causal window.
                    self.window.forget(event.dispositivo)
            self.restored = {
                item for item in self.restored if item[0] != event.dispositivo
            }
            self.restored.add(key)
        return self.window.push_sample(
            FeatureSample(
                event.dispositivo,
                event.metadata.boot_id,
                event.metadata.sequence,
                at.timestamp(),
                event.conteudo.actuators.compressor_on,
                tuple(getattr(event.conteudo.readings, field) for field in SENSORS),
            )
        )
