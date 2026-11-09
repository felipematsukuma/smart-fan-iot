"""V2 adapter to the single causal feature kernel, without wire-v1 conversion."""

from datetime import datetime
from typing import Iterable, Iterator

from .contracts_v2 import TelemetryPersistedV2, TelemetrySampleV2
from .features import SENSORS, FeatureConfig, FeatureResult, FeatureSample, FeatureWindow

TelemetryV2 = TelemetrySampleV2 | TelemetryPersistedV2


class FeatureWindowV2:
    def __init__(self, config: FeatureConfig | None = None):
        self._window = FeatureWindow(config)

    def push(self, event: TelemetryV2) -> FeatureResult:
        return self._window.push_sample(
            FeatureSample(
                event.dispositivo,
                event.metadata.boot_id,
                event.metadata.sequence,
                datetime.fromisoformat(event.timestamp).timestamp(),
                event.conteudo.actuators.compressor_on,
                tuple(getattr(event.conteudo.readings, sensor) for sensor in SENSORS),
            )
        )

    def forget(self, device_id: str) -> None:
        self._window.forget(device_id)


def iter_features_v2(
    events: Iterable[TelemetryV2], config: FeatureConfig | None = None
) -> Iterator[FeatureResult]:
    window = FeatureWindowV2(config)
    for event in events:
        yield window.push(event)
