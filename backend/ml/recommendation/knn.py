"""
KNN as a *similarity* mechanism, not a classifier.

The question this answers is not "which event will the student attend" but
"how close is each candidate event to the events this student has actually
engaged with". Nearest-neighbour distance from a candidate's feature vector to
the student's historical event vectors is turned into a similarity score, and
the caller ranks candidates by it.

Scores are **similarity scores in (0, 1]**, not probabilities. 1.0 means a
candidate is identical, in feature space, to something the student already
did; smaller means further away. They are comparable within one response and
should not be read as a likelihood of anything.

KNN is deterministic — there is no random state to set — so identical inputs
always produce identical rankings, which is what makes the behaviour testable.
"""

import numpy as np
from sklearn.neighbors import NearestNeighbors

KNN_MODEL_VERSION = 'knn-similarity-v1'
DEFAULT_NEIGHBOURS = 5


def score_candidates(*, history: np.ndarray, candidates: np.ndarray, k: int = DEFAULT_NEIGHBOURS):
    """Similarity of each candidate to the student's history.

    `history` is (n_history, n_features) and `candidates` is
    (n_candidates, n_features), both already on a common scale. Returns an
    array of (n_candidates,) similarity scores in (0, 1].

    Raises ValueError on an empty history: cold start is the caller's
    decision, made deliberately and labelled as such, never something this
    function papers over.
    """
    history = np.asarray(history, dtype=float)
    candidates = np.asarray(candidates, dtype=float)

    if history.ndim != 2 or history.shape[0] == 0:
        raise ValueError('KNN needs at least one historical event; use the cold-start path instead.')
    if candidates.ndim != 2 or candidates.shape[0] == 0:
        return np.zeros(0, dtype=float)
    if history.shape[1] != candidates.shape[1]:
        raise ValueError('history and candidates must have the same feature width')

    # Never ask for more neighbours than exist — sklearn raises otherwise.
    neighbours = max(1, min(k, history.shape[0]))
    model = NearestNeighbors(n_neighbors=neighbours, metric='euclidean')
    model.fit(history)
    distances, _indices = model.kneighbors(candidates)

    # Mean distance to the k nearest historical events, mapped onto (0, 1]:
    # distance 0 -> 1.0, and larger distances decay smoothly toward 0.
    mean_distance = distances.mean(axis=1)
    return 1.0 / (1.0 + mean_distance)
