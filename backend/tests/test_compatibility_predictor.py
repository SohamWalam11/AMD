import numpy as np

from compatibility_predictor import estimate_porting_effort, predict_compatibility_ml


def test_predict_compatibility_ml_returns_score() -> None:
    features = np.array([45, 1, 4])
    score = predict_compatibility_ml(features)
    assert 0 <= score <= 100


def test_effort_increases_with_lower_compatibility() -> None:
    low = estimate_porting_effort(40, 60)
    high = estimate_porting_effort(90, 60)
    assert low > high
