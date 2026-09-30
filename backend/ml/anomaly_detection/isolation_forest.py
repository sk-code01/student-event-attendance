"""
Isolation Forest over structured evidence features.

**What the output is:** an internal *risk signal* — a measure of how isolated a
record's feature vector is from the rest of the population. **What it is not:**
a fraud determination, a probability, or a calibrated likelihood. There are no
ground-truth "fraudulent" labels in this system, so no accuracy, precision or
recall can honestly be quoted, and none is.

Every threshold below is relative to the fitted population's own score
distribution (percentiles), so "HIGH" means "among the most isolated records
in this dataset", never an absolute claim about the record. The thresholds are
returned alongside the scores so they are documented in the response itself.

A human reviewer decides what, if anything, a signal means. Nothing here
rejects, verifies or approves.
"""

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

ISOLATION_FOREST_MODEL_VERSION = 'isolation-forest-v1'

# Below this the forest is fitting noise; the caller reports INSUFFICIENT_DATA.
MIN_SAMPLES = 5

# Percentiles of the population's anomaly-score distribution.
HIGH_PERCENTILE = 90
MEDIUM_PERCENTILE = 75


class RiskLevel:
    LOW = 'LOW'
    MEDIUM = 'MEDIUM'
    HIGH = 'HIGH'


class InsufficientData(ValueError):
    """Fewer than MIN_SAMPLES rows: the model would be fitting noise."""


@dataclass
class ForestResult:
    anomaly_scores: np.ndarray   # higher = more isolated / unusual
    is_outlier: np.ndarray       # sklearn's own predict() == -1
    levels: list                 # RiskLevel per row
    high_threshold: float
    medium_threshold: float
    n_samples: int
    n_features: int


def fit_and_score(features: np.ndarray, *, random_state: int = 42) -> ForestResult:
    """Fits on `features` (n_samples, n_features) and scores every row.

    The model is fitted on the population it scores — this is unsupervised
    outlier detection over the current dataset, not a persisted model applied
    to new data. `random_state` is fixed so the same inputs give the same
    scores, which is what makes the behaviour testable.
    """
    features = np.asarray(features, dtype=float)
    if features.ndim != 2 or features.shape[0] < MIN_SAMPLES:
        raise InsufficientData(
            f'Isolation Forest needs at least {MIN_SAMPLES} records; '
            f'got {0 if features.ndim != 2 else features.shape[0]}.',
        )

    # NaN would poison every tree; missing values are imputed to the column
    # median so an absent measurement reads as "typical", not as an outlier.
    features = _impute_median(features)

    scaled = StandardScaler().fit_transform(features)
    forest = IsolationForest(
        n_estimators=100, contamination='auto', random_state=random_state,
    )
    forest.fit(scaled)

    # score_samples is "higher = more normal"; negate so the reported number
    # reads intuitively as "higher = more unusual".
    anomaly_scores = -forest.score_samples(scaled)
    is_outlier = forest.predict(scaled) == -1

    high_threshold = float(np.percentile(anomaly_scores, HIGH_PERCENTILE))
    medium_threshold = float(np.percentile(anomaly_scores, MEDIUM_PERCENTILE))

    levels = []
    for score, outlier in zip(anomaly_scores, is_outlier):
        # HIGH needs both signals to agree: the forest calls it an outlier AND it
        # sits in the top decile of isolation. MEDIUM needs either. That makes
        # HIGH deliberately conservative — a reviewer's attention is expensive.
        if outlier and score >= high_threshold:
            levels.append(RiskLevel.HIGH)
        elif outlier or score >= medium_threshold:
            levels.append(RiskLevel.MEDIUM)
        else:
            levels.append(RiskLevel.LOW)

    return ForestResult(
        anomaly_scores=anomaly_scores,
        is_outlier=is_outlier,
        levels=levels,
        high_threshold=high_threshold,
        medium_threshold=medium_threshold,
        n_samples=features.shape[0],
        n_features=features.shape[1],
    )


def _impute_median(features: np.ndarray) -> np.ndarray:
    out = features.copy()
    for column in range(out.shape[1]):
        col = out[:, column]
        mask = np.isnan(col)
        if mask.any():
            fill = np.nanmedian(col) if (~mask).any() else 0.0
            col[mask] = fill
    return out
