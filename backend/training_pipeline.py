from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
from joblib import dump
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score


def _load_dataset(dataset_path: str | None) -> tuple[np.ndarray, np.ndarray]:
    if dataset_path and Path(dataset_path).exists():
        rows = [line.strip().split(",") for line in Path(dataset_path).read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(rows) > 1:
            header = rows[0]
            data = rows[1:]
            index = {name: i for i, name in enumerate(header)}
            features = []
            targets = []
            for row in data:
                features.append(
                    [
                        float(row[index["kernel_complexity"]]),
                        float(row[index["memory_patterns"]]),
                        float(row[index["api_usage"]]),
                    ]
                )
                targets.append(int(row[index["compatibility_category"]]))
            return np.array(features), np.array(targets)

    features = np.array(
        [
            [20, 0, 2],
            [35, 1, 3],
            [50, 1, 5],
            [65, 2, 6],
            [80, 3, 7],
            [90, 4, 8],
            [30, 0, 1],
            [45, 1, 4],
            [75, 3, 6],
            [55, 2, 5],
            [70, 2, 6],
        ]
    )
    targets = np.array([2, 2, 1, 1, 0, 0, 2, 1, 0, 1, 0])
    return features, targets


def train_calibrated_model(dataset_path: str | None, output_path: str) -> Dict[str, Any]:
    features, targets = _load_dataset(dataset_path)
    estimator = RandomForestClassifier(n_estimators=120, random_state=42)
    cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)

    scores = cross_val_score(estimator, features, targets, cv=cv, scoring="accuracy")

    calibrated = CalibratedClassifierCV(estimator, method="sigmoid", cv=3)
    calibrated.fit(features, targets)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    dump(calibrated, out)

    metrics = {
        "accuracy_mean": float(scores.mean()),
        "accuracy_std": float(scores.std()),
        "samples": int(features.shape[0]),
        "features": int(features.shape[1]),
        "model_path": str(out),
    }

    metrics_file = out.with_suffix(".metrics.json")
    metrics_file.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics
