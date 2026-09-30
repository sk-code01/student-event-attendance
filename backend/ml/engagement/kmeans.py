"""
K-Means engagement clustering with **centroid-ordered labels**.

K-Means cluster ids are arbitrary: cluster 0 is not "low" and cluster 2 is not
"high" — the assignment depends on initialisation and can flip between fits.
So the human-readable label is never taken from the cluster id. Instead, each
centroid is scored with a documented engagement formula in original feature
units, the centroids are sorted by that score, and LOW / MODERATE / HIGH are
assigned in that order. That is what makes the labels stable and testable.

This is analytics, not an academic judgment: "LOW engagement" describes a
pattern of counts, not a student's worth or standing.

Small-data policy (deterministic, documented):
    0 rows -> InsufficientData (caller reports unavailable)
    1 row  -> InsufficientData (one point cannot be clustered)
    2 rows -> K = 2, labelled LOW / HIGH
    3+     -> K = 3, labelled LOW / MODERATE / HIGH
K is additionally capped at the number of *distinct* feature vectors, since
K-Means cannot form more clusters than there are distinct points; if that
leaves K = 1, every student is labelled MODERATE and the response says why.
"""

from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

KMEANS_MODEL_VERSION = 'kmeans-engagement-v1'


class EngagementLabel:
    LOW = 'LOW'
    MODERATE = 'MODERATE'
    HIGH = 'HIGH'


class InsufficientData(ValueError):
    """Fewer than two students: nothing to cluster."""


@dataclass
class ClusterResult:
    labels: list                  # EngagementLabel per row, in input order
    cluster_ids: np.ndarray       # raw sklearn cluster id per row (diagnostic only)
    k: int
    centroids: np.ndarray         # in ORIGINAL feature units, ordered by engagement score ascending
    centroid_scores: list         # engagement score per ordered centroid
    label_order: list             # labels in ascending engagement order
    n_samples: int
    n_features: int
    note: str = ''


def _choose_k(n_samples: int, n_distinct: int) -> int:
    if n_samples < 2:
        raise InsufficientData('At least two students are required to cluster engagement.')
    k = 2 if n_samples == 2 else 3
    return max(1, min(k, n_distinct))


def _labels_for_k(k: int) -> list:
    if k >= 3:
        return [EngagementLabel.LOW, EngagementLabel.MODERATE, EngagementLabel.HIGH]
    if k == 2:
        return [EngagementLabel.LOW, EngagementLabel.HIGH]
    return [EngagementLabel.MODERATE]


def cluster_students(features: np.ndarray, *, weights: np.ndarray, random_state: int = 42) -> ClusterResult:
    """Clusters (n_students, n_features) and returns ordered labels.

    `weights` (n_features,) defines the engagement score used to order the
    centroids: score = centroid_in_original_units . weights. The caller owns
    and documents the weights; this function only applies them.
    """
    features = np.asarray(features, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if features.ndim != 2:
        raise InsufficientData('Feature matrix must be two-dimensional.')
    n_samples = features.shape[0]
    if n_samples < 2:
        raise InsufficientData('At least two students are required to cluster engagement.')
    if weights.shape[0] != features.shape[1]:
        raise ValueError('weights must have one entry per feature')

    features = np.nan_to_num(features, nan=0.0)
    n_distinct = len({tuple(row) for row in features.tolist()})
    k = _choose_k(n_samples, n_distinct)

    note = ''
    if k == 1:
        # Every student has an identical feature vector: there is no
        # ordering to express, so nobody is "lower" than anyone else.
        return ClusterResult(
            labels=[EngagementLabel.MODERATE] * n_samples,
            cluster_ids=np.zeros(n_samples, dtype=int),
            k=1,
            centroids=features[:1].copy(),
            centroid_scores=[float(features[0] @ weights)],
            label_order=[EngagementLabel.MODERATE],
            n_samples=n_samples,
            n_features=features.shape[1],
            note='All students have identical engagement features; a single group was formed.',
        )

    scaler = StandardScaler()
    scaled = scaler.fit_transform(features)
    model = KMeans(n_clusters=k, n_init=10, random_state=random_state)
    cluster_ids = model.fit_predict(scaled)

    # Score centroids in ORIGINAL units so the documented weights mean what
    # they say (a weight of 3 on "participations" is 3 per participation, not
    # 3 per standard deviation).
    centroids_original = scaler.inverse_transform(model.cluster_centers_)
    centroid_scores = centroids_original @ weights
    order = np.argsort(centroid_scores, kind='stable')  # ascending engagement

    label_names = _labels_for_k(k)
    cluster_to_label = {int(cluster_id): label_names[rank] for rank, cluster_id in enumerate(order)}

    return ClusterResult(
        labels=[cluster_to_label[int(c)] for c in cluster_ids],
        cluster_ids=cluster_ids,
        k=k,
        centroids=centroids_original[order],
        centroid_scores=[float(centroid_scores[i]) for i in order],
        label_order=label_names,
        n_samples=n_samples,
        n_features=features.shape[1],
        note=note,
    )
