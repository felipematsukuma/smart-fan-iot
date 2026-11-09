"""Optional ML imports, used only by training/inference processes and trusted bundles."""

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


def predict_target(model: Any, X: Any, target: str) -> Any:
    if target not in ("health_score", "rul_calendar_hours"):
        raise ValueError("Unknown regression target")
    values = np.asarray(model.predict(X), dtype=np.float64)
    return np.clip(values, 0, 100) if target == "health_score" else np.maximum(values, 0)


class TrainingQuantiles(TransformerMixin, BaseEstimator):  # type: ignore[misc]  # sklearn has no PEP 561 marker.
    """Bounds are fitted exclusively on the training equipment, before prediction."""

    def __init__(self, lower: float = 0.01, upper: float = 0.99):
        self.lower = lower
        self.upper = upper

    def fit(self, X: Any, y: Any = None) -> "TrainingQuantiles":
        values = np.asarray(X, dtype=np.float64)
        self.low_ = np.nanquantile(values, self.lower, axis=0)
        self.high_ = np.nanquantile(values, self.upper, axis=0)
        self.n_features_in_ = values.shape[1]
        return self

    def transform(self, X: Any) -> Any:
        values = np.asarray(X, dtype=np.float64)
        if values.ndim != 2 or values.shape[1] != self.n_features_in_:
            raise ValueError("Feature dimensions differ")
        return np.clip(values, self.low_, self.high_)
