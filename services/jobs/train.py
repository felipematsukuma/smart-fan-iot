"""Grouped evaluation of independent health/RUL regressors; no live labels are read."""

import hashlib
import json
import math
import os
import signal
import sys
import time
from pathlib import Path

from smartfan_common.training_config import TrainingTask

from .generate import canonical, digest_file, generate, progress

TARGETS = ("health_score", "rul_calendar_hours")


class TrainingDataError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def dataset_manifest(path: Path, expected: str, cancel) -> dict:
    manifest = json.loads((path / "manifest.json").read_bytes())
    content = manifest["content"]
    if (
        manifest["sha256"] != expected
        or hashlib.sha256(canonical(content)).hexdigest() != expected
    ):
        raise ValueError("Dataset manifest changed")
    expected_files = {
        "readings.npy",
        "timestamp_seconds.npy",
        "equipment_index.npy",
        "compressor_on.npy",
        "condenser_fan_on.npy",
        "health_score.npy",
        "rul_calendar_hours.npy",
        "censored.npy",
        "outliers.npy",
    }
    if set(content["files"]) != expected_files:
        raise ValueError("Unexpected dataset files")
    for name, digest in content["files"].items():
        if digest_file(path / name, cancel) != digest:
            raise ValueError("Dataset bytes changed")
    return manifest


def metrics(y, prediction) -> dict:
    import numpy as np
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

    if len(y) < 2 or not np.isfinite(y).all() or not np.isfinite(prediction).all():
        return {
            "mae": None,
            "rmse": None,
            "r2": None,
            "reason": "insufficient_finite_samples",
            "count": len(y),
        }
    variable = float(np.var(y)) > 1e-12
    return {
        "mae": float(mean_absolute_error(y, prediction)),
        "rmse": math.sqrt(float(mean_squared_error(y, prediction))),
        "r2": float(r2_score(y, prediction)) if variable else None,
        "reason": None if variable else "constant_target",
        "count": len(y),
    }


def predict(model, X, target):
    from smartfan_common.ml_pipeline import predict_target

    return predict_target(model, X, target)


def fit_model(algorithm: str, X, y, seed: int):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from smartfan_common.ml_pipeline import TrainingQuantiles

    stages = [
        ("train_quantiles", TrainingQuantiles()),
        ("train_imputer", SimpleImputer(strategy="median")),
    ]
    if algorithm == "ridge":
        stages.extend(
            [("train_scaler", StandardScaler()), ("regressor", Ridge(alpha=10))]
        )
    else:
        stages.append(
            (
                "regressor",
                HistGradientBoostingRegressor(
                    max_iter=80,
                    max_leaf_nodes=15,
                    max_depth=5,
                    learning_rate=0.08,
                    l2_regularization=1,
                    early_stopping=False,
                    random_state=seed,
                ),
            )
        )
    return Pipeline(stages).fit(X, y)


def train(task: TrainingTask, path: Path, root: Path, cancel=lambda: False) -> dict:
    # Imports happen only after the independent parent watchdog starts in main().
    import importlib

    import joblib
    import numpy as np
    import sklearn
    from sklearn.dummy import DummyRegressor
    from sklearn.inspection import permutation_importance
    from smartfan_common.model_policy import promotion_reasons
    from threadpoolctl import threadpool_limits

    from .batch_features import extract

    started = time.monotonic()
    path.mkdir(parents=True, exist_ok=True)

    def checkpoint(percent):
        if cancel():
            raise InterruptedError("Training cancelled")
        progress(path, percent, 100)

    checkpoint(1)
    source = root / "datasets" / task.request.dataset_id
    manifest = dataset_manifest(source, task.dataset_sha256, cancel)
    if manifest["content"]["configuration"] != task.source_config.model_dump(
        exclude={"block_size"}
    ):
        raise ValueError("Source configuration differs from artifact")
    checkpoint(5)
    data = extract(
        source, manifest, task.request.max_feature_rows, task.request.seed, cancel
    )
    checkpoint(25)
    X = data["X"]
    labels = data["y"]
    group_ids = np.unique(data["groups"])
    if len(group_ids) < 10:
        raise TrainingDataError("insufficient_equipment_groups")
    rng = np.random.default_rng(task.request.seed)
    available = np.array(
        [
            group
            for group in group_ids
            if np.isfinite(labels[data["groups"] == group, 1]).any()
        ]
    )
    if len(available) < 5:
        raise TrainingDataError("insufficient_observed_failures")
    observed_order = rng.permutation(available)
    other_order = rng.permutation(np.setdiff1d(group_ids, available))
    holdout = max(2, round(len(group_ids) * 0.2))
    failure_holdout = max(1, round(len(available) * 0.2))
    other_holdout = holdout - failure_holdout
    groups = {
        "test": np.r_[observed_order[:failure_holdout], other_order[:other_holdout]],
        "validation": np.r_[
            observed_order[failure_holdout : 2 * failure_holdout],
            other_order[other_holdout : 2 * other_holdout],
        ],
        "train": np.r_[
            observed_order[2 * failure_holdout :], other_order[2 * other_holdout :]
        ],
    }
    if (
        set(groups["train"]) & set(groups["validation"])
        or set(groups["train"]) & set(groups["test"])
        or set(groups["test"]) & set(groups["validation"])
    ):
        raise ValueError("Equipment split overlaps")
    masks = {name: np.isin(data["groups"], values) for name, values in groups.items()}
    models = {}
    baselines = {}
    targets = {}
    selection = {}
    with threadpool_limits(limits=1):
        for target_index, target in enumerate(TARGETS):
            finite = np.isfinite(labels[:, target_index])
            y = labels[:, target_index]
            train_mask = masks["train"] & finite
            validation_mask = masks["validation"] & finite
            test_mask = masks["test"] & finite
            if (
                train_mask.sum() < 100
                or validation_mask.sum() < 20
                or test_mask.sum() < 20
                or np.var(y[train_mask]) <= 1e-12
            ):
                raise TrainingDataError(target + "_insufficient_variation")
            baseline = DummyRegressor(strategy="mean").fit(X[train_mask], y[train_mask])
            baselines[target] = baseline
            candidates = {}
            fitted = {}
            for algorithm in ["ridge", "hist_gradient_boosting"]:
                if cancel():
                    raise InterruptedError("Training cancelled")
                model = fit_model(
                    algorithm, X[train_mask], y[train_mask], task.request.seed
                )
                fitted[algorithm] = model
                candidates[algorithm] = metrics(
                    y[validation_mask], predict(model, X[validation_mask], target)
                )
            chosen = min(
                candidates,
                key=lambda name: (
                    candidates[name]["mae"]
                    if candidates[name]["mae"] is not None
                    else float("inf")
                ),
            )
            model = fitted[chosen]
            models[target] = model
            selection[target] = chosen
            prediction = predict(model, X[test_mask], target)
            indices = np.flatnonzero(test_mask)
            plot = rng.choice(len(indices), size=min(200, len(indices)), replace=False)
            targets[target] = {
                "selected_algorithm": chosen,
                "validation_candidates": candidates,
                "validation_baseline": metrics(
                    y[validation_mask], baseline.predict(X[validation_mask])
                ),
                "test": metrics(y[test_mask], prediction),
                "test_baseline": metrics(y[test_mask], baseline.predict(X[test_mask])),
                "scatter": [
                    {
                        "real": float(y[indices[index]]),
                        "predicted": float(prediction[index]),
                    }
                    for index in plot
                ],
                "censored_excluded": int((~finite).sum()),
                "train_samples": int(train_mask.sum()),
                "validation_samples": int(validation_mask.sum()),
                "test_samples": int(test_mask.sum()),
            }
            checkpoint(45 + target_index * 15)
        benchmark_config = task.source_config.model_copy(
            update={"seed": task.request.benchmark_seed}
        )
        benchmark_manifest = generate(benchmark_config, path / "benchmark", cancel)
        benchmark = extract(
            path / "benchmark",
            benchmark_manifest,
            task.request.benchmark_feature_rows,
            task.request.seed + 1,
            cancel,
        )
        checkpoint(75)
        active = None
        if task.active_model_version:
            active_bundle = (
                root / "models" / task.active_model_version / "bundle.joblib"
            )
            if digest_file(active_bundle, cancel) != task.active_bundle_sha256:
                raise ValueError("Active bundle hash changed")
            active = joblib.load(active_bundle)
            if (
                active["feature_names"] != data["feature_names"]
                or active["feature_version"] != data["feature_version"]
                or active["feature_config"] != data["feature_config"]
                or active["rul_unit"] != "calendar_hours"
            ):
                raise ValueError("Active features not comparable")
        for target_index, target in enumerate(TARGETS):
            y = benchmark["y"][:, target_index]
            valid = np.isfinite(y)
            observed = benchmark["X"][valid]
            truth = y[valid]
            predicted = (
                predict(models[target], observed, target) if len(truth) else np.empty(0)
            )
            targets[target]["benchmark"] = metrics(truth, predicted)
            targets[target]["benchmark_baseline"] = metrics(
                truth,
                baselines[target].predict(observed) if len(truth) else np.empty(0),
            )
            active_pred = (
                (
                    predict(active["models"][target], observed, target)
                    if len(truth)
                    else np.empty(0)
                )
                if active
                else None
            )
            targets[target]["benchmark_active"] = (
                metrics(truth, active_pred) if active else None
            )
            per_mode = {}
            for mode in np.unique(benchmark["modes"][valid]):
                mask = benchmark["modes"][valid] == mode
                per_mode[str(mode)] = {
                    "count": int(mask.sum()),
                    "mae": float(np.mean(np.abs(truth[mask] - predicted[mask]))),
                    "active_mae": float(
                        np.mean(np.abs(truth[mask] - active_pred[mask]))
                    )
                    if active_pred is not None
                    else None,
                }
            targets[target]["per_mode"] = per_mode
            healthy = benchmark["modes"][valid] == "healthy"
            targets[target]["healthy_samples"] = int(healthy.sum())
            targets[target]["healthy_false_positive_fraction"] = (
                float(np.mean(predicted[healthy] < 40))
                if target == "health_score" and healthy.any()
                else None
            )
            indices = np.flatnonzero(
                masks["validation"] & np.isfinite(labels[:, target_index])
            )
            chosen_rows = rng.choice(
                indices,
                size=min(task.request.importance_rows, len(indices)),
                replace=False,
            )

            def score(estimator, features, target_values, chosen_target=target):
                return -float(
                    np.mean(
                        np.abs(
                            target_values - predict(estimator, features, chosen_target)
                        )
                    )
                )

            importance = permutation_importance(
                models[target],
                X[chosen_rows],
                labels[chosen_rows, target_index],
                scoring=score,
                n_repeats=2,
                random_state=task.request.seed,
                n_jobs=1,
            )
            targets[target]["feature_importance"] = [
                {"feature": name, "importance": float(mean), "std": float(std)}
                for name, mean, std in zip(
                    data["feature_names"],
                    importance.importances_mean,
                    importance.importances_std,
                    strict=True,
                )
            ]
            checkpoint(85 + target_index * 5)

        def identity(group):
            return (
                task.dataset_sha256[:12]
                + ":"
                + manifest["content"]["devices"][int(group)]["id"]
            )

        split = {
            name: [identity(group) for group in values]
            for name, values in groups.items()
        }
        report = {
            "format_version": 1,
            "model_version": task.model_version,
            "dataset_id": task.request.dataset_id,
            "dataset_sha256": task.dataset_sha256,
            "active_reference_version": task.active_model_version,
            "feature_version": data["feature_version"],
            "feature_names": data["feature_names"],
            "feature_config": data["feature_config"],
            "rul_unit": "calendar_hours",
            "algorithms": ["ridge", "hist_gradient_boosting"],
            "targets": targets,
            "split": split,
            "split_sha256": hashlib.sha256(canonical(split)).hexdigest(),
            "benchmark_sha256": benchmark_manifest["sha256"],
            "benchmark_seed": task.request.benchmark_seed,
            "benchmark_equipment_ids": [
                benchmark_manifest["sha256"][:12] + ":" + device["id"]
                for device in benchmark_manifest["content"]["devices"]
            ],
            "feature_statuses": data["statuses"],
            "source_rows": manifest["content"]["rows"],
            "feature_rows": len(X),
            "leakage_controls": {
                "observed_only": True,
                "causal_windows": True,
                "equipment_split": True,
                "preprocessing_fitted_on_train_only": True,
                "excluded": [
                    "health_score",
                    "rul_calendar_hours",
                    "censored",
                    "failure_mode",
                    "equipment_id",
                    "seed",
                    "latent_damage",
                ],
            },
            "limitations": [
                "Dados sintéticos do próprio gerador; não é vida útil calibrada de fabricante.",
                "RUL não observada é excluída, podendo enviesar a população de falhas.",
                "Tempo sintético e taxa de degradação não substituem validação externa.",
            ],
            "versions": {"numpy": np.__version__, "scikit_learn": sklearn.__version__},
            "hyperparameters": {
                "ridge": {"alpha": 10},
                "hist_gradient_boosting": {
                    "max_iter": 80,
                    "max_leaf_nodes": 15,
                    "max_depth": 5,
                    "learning_rate": 0.08,
                    "l2_regularization": 1,
                    "early_stopping": False,
                    "random_state": task.request.seed,
                },
                "train_quantiles": [0.01, 0.99],
                "imputer": "train_median",
                "ridge_scaler": "train_standard_scaler",
            },
            "split_strategy": "60/20/20 equipment groups stratified by observed RUL availability; labels never enter features",
        }
        report["promotion_reasons"] = promotion_reasons(
            report, task.active_model_version
        )
        report["eligible"] = not report["promotion_reasons"]
        train_observed = X[masks["train"]]
        bundle = {
            "models": models,
            "feature_names": data["feature_names"],
            "feature_version": data["feature_version"],
            "feature_config": data["feature_config"],
            "rul_unit": "calendar_hours",
            "model_version": task.model_version,
            "drift_low": np.quantile(train_observed, 0.01, axis=0),
            "drift_high": np.quantile(train_observed, 0.99, axis=0),
        }
        joblib.dump(bundle, path / "bundle.joblib", compress=3)
        (path / "report.json").write_bytes(canonical(report))
        card = f"# Model card {task.model_version}\n\nDois regressores independentes: saúde e RUL em horas de calendário.\n\nDataset {task.dataset_sha256}; features {data['feature_version']}; split por equipamento.\n\nAlgoritmos escolhidos: {json.dumps(selection)}. Baseline: média ajustada somente no treino.\n\nLimitações: dados sintéticos, censura de RUL, sem calibração real de fabricante.\n\nElegível pela política: {report['eligible']}; motivos {json.dumps(report['promotion_reasons'])}. Aprovação não implica ativação.\n"
        (path / "model-card.md").write_text(card, encoding="utf-8")
        names = [
            "bundle.joblib",
            "report.json",
            "model-card.md",
            "benchmark/manifest.json",
        ] + ["benchmark/" + name for name in benchmark_manifest["content"]["files"]]
        files = {name: digest_file(path / name, cancel) for name in names}
        content = {
            "format_version": 1,
            "model_version": task.model_version,
            "task": task.model_dump(),
            "feature_version": data["feature_version"],
            "feature_names": data["feature_names"],
            "feature_config": data["feature_config"],
            "rul_unit": "calendar_hours",
            "files": files,
            "report": report,
        }
        manifest = {
            "content": content,
            "sha256": hashlib.sha256(canonical(content)).hexdigest(),
            "execution": {
                "seconds": time.monotonic() - started,
                "peak_rss_mib": importlib.import_module("resource")
                .getrusage(0)
                .ru_maxrss
                / 1024
                if os.name == "posix"
                else None,
            },
        }
        (path / "manifest.json").write_bytes(canonical(manifest))
        checkpoint(100)
        return manifest


def main() -> None:
    from .child_guard import supervise_parent

    path = Path(sys.argv[1])
    supervise_parent(path)
    cancelled = False

    def stop(*_):
        nonlocal cancelled
        cancelled = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    task = TrainingTask.model_validate_json((path / "config.json").read_bytes())
    try:
        train(
            task,
            path,
            path.parents[1],
            lambda: cancelled or (path / "cancel.requested").exists(),
        )
    except InterruptedError:
        raise SystemExit(2) from None
    except (ValueError, TypeError) as error:
        (path / "error.json").write_bytes(
            canonical(
                {
                    "reason": error.code
                    if isinstance(error, TrainingDataError)
                    else "training_data_or_artifact_invalid"
                }
            )
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
