"""
The AI service layer: orchestration plus the failure boundary.

Every public function here returns a plain dict with an `available` flag and
never raises. Two things guarantee that:

  * `_decision_support` wraps each function. `InsufficientData` becomes
    `available: False, reason: INSUFFICIENT_DATA`; any other exception becomes
    `reason: MODEL_ERROR`, is logged with its traceback, and the client sees a
    controlled payload rather than a Python error.
  * These functions are only ever called from GET endpoints. No business
    service (registration, participation, verification, attendance, OD,
    achievement, notification) calls into this module, so an AI failure has no
    transaction to roll back. That is by construction, and the workflow-safety
    tests pin it.

**Nothing here decides anything.** The recommender ranks, the forest scores,
K-Means labels. Faculty verify, Event Coordinators approve, students register — the same as
before Phase 8.
"""

import functools
import logging
import time

import numpy as np
from django.utils import timezone

from apps.analytics.scope import AnalyticsScope
from ml.anomaly_detection import isolation_forest as forest_model
from ml.engagement import kmeans as kmeans_model
from ml.recommendation import knn as knn_model

from . import features

logger = logging.getLogger(__name__)

DISCLAIMER = (
    'AI-generated decision-support signal. Final academic decisions remain with '
    'authorized Faculty/Event Coordinator personnel.'
)

# A student needs at least this many engaged events for KNN to say anything a
# deterministic rule could not; below it the cold-start path is used and
# labelled honestly.
MIN_HISTORY_FOR_KNN = 1
DEFAULT_LIMIT = 10


class InsufficientData(ValueError):
    pass


def _decision_support(model_name):
    """Failure boundary. See module docstring."""

    def decorate(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            try:
                payload = fn(*args, **kwargs)
            except (InsufficientData, forest_model.InsufficientData, kmeans_model.InsufficientData) as exc:
                payload = _unavailable(model_name, 'INSUFFICIENT_DATA', str(exc))
            except Exception:  # noqa: BLE001 - this is the point of the boundary
                logger.exception('AI %s failed; returning controlled fallback', model_name)
                payload = _unavailable(
                    model_name, 'MODEL_ERROR',
                    'The model could not be evaluated. Core workflows are unaffected.',
                )
            payload.setdefault('generated_at', timezone.now())
            payload.setdefault('disclaimer', DISCLAIMER)
            payload['inference_ms'] = round((time.perf_counter() - started) * 1000, 1)
            return payload
        return wrapper
    return decorate


def _unavailable(model_name, reason, detail=''):
    return {
        'available': False,
        'model': model_name,
        'reason': reason,
        'detail': detail,
        'results': [],
    }


# =========================================================================== #
# Recommendations                                                             #
# =========================================================================== #

@_decision_support('knn')
def recommend_events(student, *, limit=DEFAULT_LIMIT, today=None) -> dict:
    """Ranked, actionable events for `student` with feature-backed reasons.

    Scope is the student themselves — the caller passes `request.user` and
    there is no parameter by which to name anyone else.
    """
    today = today or timezone.localdate()
    vectors = features.build_event_vectors(student, today=today)

    if not vectors.candidate_events:
        return {
            'available': True, 'model': 'knn' if vectors.history_events else 'cold_start',
            'reason': 'NO_ACTIONABLE_EVENTS',
            'detail': 'There are no events currently open for registration that you have not already registered for.',
            'results': [],
            'history_size': len(vectors.history_events),
        }

    history_categories = {(e.category or '').strip().lower() for e in vectors.history_events}
    popularity_median = float(np.median(
        [vectors.popularity.get(e.id, 0) for e in vectors.candidate_events],
    )) if vectors.candidate_events else 0.0

    if len(vectors.history_events) >= MIN_HISTORY_FOR_KNN:
        model = 'knn'
        scores = knn_model.score_candidates(history=vectors.history, candidates=vectors.candidates)
        score_basis = (
            'KNN similarity in (0, 1]: 1.0 means identical, in feature space, to an event you '
            'already engaged with. Not a probability.'
        )
    else:
        model = 'cold_start'
        scores = _cold_start_scores(student, vectors, today)
        score_basis = (
            'Deterministic cold-start ranking: department relevance, current popularity and '
            'how soon the event is. Not a model output and not a probability.'
        )

    results = []
    for event, score in zip(vectors.candidate_events, scores):
        reasons = _recommendation_reasons(
            event, student, vectors, history_categories, popularity_median, today, model,
        )
        results.append({
            'event_id': event.id,
            'score': round(float(score), 4),
            'reasons': reasons,
            'event': {
                'id': event.id,
                'title': event.title,
                'category': event.category,
                'event_date': event.event_date,
                'venue': event.venue,
                'registration_end_date': event.registration_end_date,
                'department': event.department.name if event.department_id else None,
            },
        })

    # Score descending, then soonest, then id — fully deterministic.
    results.sort(key=lambda r: (-r['score'], r['event']['event_date'], r['event_id']))
    return {
        'available': True,
        'model': model,
        'model_version': knn_model.KNN_MODEL_VERSION if model == 'knn' else 'cold-start-v1',
        'feature_version': features.FEATURE_VERSION,
        'score_basis': score_basis,
        'history_size': len(vectors.history_events),
        'candidate_count': len(vectors.candidate_events),
        'results': results[:limit],
    }


def _cold_start_scores(student, vectors, today):
    """Documented deterministic ranking for students with no history."""
    scores = []
    for event in vectors.candidate_events:
        dept = 1.0 if (event.department_id is not None and event.department_id == student.department_id) else 0.0
        pop = (vectors.popularity.get(event.id, 0) / vectors.max_popularity) if vectors.max_popularity else 0.0
        days = max((event.event_date - today).days, 0)
        soon = 1.0 - min(days, features.RECENCY_HORIZON_DAYS) / features.RECENCY_HORIZON_DAYS
        scores.append(0.5 * dept + 0.3 * pop + 0.2 * soon)
    return np.array(scores)


def _recommendation_reasons(event, student, vectors, history_categories, popularity_median, today, model):
    """Only reasons the underlying features actually support."""
    reasons = []
    category = (event.category or '').strip()
    if model == 'knn' and category.lower() in history_categories:
        reasons.append(f'Matches a category you have engaged with before ({category}).')
    if event.department_id is not None and event.department_id == student.department_id:
        reasons.append('Organised by your department.')
    live = vectors.popularity.get(event.id, 0)
    if live > 0 and live >= popularity_median and vectors.max_popularity > 0:
        reasons.append(f'Popular with other students ({live} registered).')
    days = (event.event_date - today).days
    if 0 <= days <= 14:
        reasons.append(f'Coming up soon (in {days} day{"s" if days != 1 else ""}).')
    if not reasons:
        reasons.append('Open for registration now.')
    return reasons


# =========================================================================== #
# Anomaly / risk signals                                                      #
# =========================================================================== #

@_decision_support('isolation_forest')
def evidence_risk_signals(*, scope: AnalyticsScope, evidence_id=None, limit=100) -> dict:
    """Risk signals for evidence the caller may already see.

    The forest is fitted on the **whole** evidence population (an identity-free
    feature matrix) so a level means the same thing regardless of who asks;
    only rows inside `scope` are returned. An `evidence_id` outside the scope
    is a 404 at the view layer before this runs.
    """
    from apps.verification.models import Evidence

    population = features.build_evidence_features(Evidence.objects.all())
    result = forest_model.fit_and_score(population.matrix)

    scoped_ids = set(scope.evidence().values_list('id', flat=True))
    if evidence_id is not None:
        scoped_ids &= {evidence_id}

    index_by_id = {eid: i for i, eid in enumerate(population.evidence_ids)}
    detail_rows = {
        row['id']: row
        for row in scope.evidence().filter(id__in=scoped_ids)
        .values('id', 'participation_id', 'status', 'participation__student__username',
                'participation__event__title', 'participation__event__id')
    }

    results = []
    for eid in sorted(scoped_ids):
        i = index_by_id.get(eid)
        if i is None:
            continue
        values = population.rows[eid]
        detail = detail_rows.get(eid, {})
        results.append({
            'evidence_id': eid,
            'participation_id': detail.get('participation_id'),
            'student': detail.get('participation__student__username'),
            'event_id': detail.get('participation__event__id'),
            'event_title': detail.get('participation__event__title'),
            'effective_decision': detail.get('status'),
            'risk_level': result.levels[i],
            'anomaly_score': round(float(result.anomaly_scores[i]), 4),
            'signals': _anomaly_signals(values, population.population_medians),
            'features': {k: (None if (isinstance(v, float) and np.isnan(v)) else round(float(v), 3))
                         for k, v in values.items()},
        })

    order = {forest_model.RiskLevel.HIGH: 0, forest_model.RiskLevel.MEDIUM: 1, forest_model.RiskLevel.LOW: 2}
    results.sort(key=lambda r: (order[r['risk_level']], -r['anomaly_score'], r['evidence_id']))

    return {
        'available': True,
        'model': 'isolation_forest',
        'model_version': forest_model.ISOLATION_FOREST_MODEL_VERSION,
        'feature_version': features.FEATURE_VERSION,
        'score_basis': (
            'Negated Isolation Forest score_samples: higher = more isolated from the population. '
            'An internal risk signal, not a probability and not a fraud determination.'
        ),
        'thresholds': {
            'high': round(result.high_threshold, 4),
            'medium': round(result.medium_threshold, 4),
            'rule': (
                f'HIGH = flagged as outlier by the forest AND score >= the {forest_model.HIGH_PERCENTILE}th '
                f'percentile of the population; MEDIUM = either; otherwise LOW.'
            ),
        },
        'population': {'n_samples': result.n_samples, 'n_features': result.n_features},
        'feature_definitions': [
            {'name': name, 'temporal_status': status} for name, status in features.ANOMALY_FEATURES
        ],
        'summary': {
            level: sum(1 for r in results if r['risk_level'] == level)
            for level in (forest_model.RiskLevel.HIGH, forest_model.RiskLevel.MEDIUM, forest_model.RiskLevel.LOW)
        },
        'results': results[:limit],
    }


def _anomaly_signals(values, medians):
    """Human-readable signals, emitted only when the feature actually
    exceeds a stated threshold. Nothing is inferred beyond the numbers."""
    signals = []

    def val(name):
        v = values.get(name)
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else v

    distance = val('max_venue_distance_m')
    if distance is not None and distance > 200 and distance > 2 * max(medians.get('max_venue_distance_m', 0), 1):
        signals.append(f'Capture taken {distance:.0f} m from the venue '
                       f'(typical: {medians["max_venue_distance_m"]:.0f} m).')

    versions = val('version_count')
    if versions is not None and versions >= 2:
        signals.append(f'Evidence resubmitted {int(versions) - 1} time{"s" if versions != 2 else ""}.')

    delay = val('mean_upload_delay_s')
    if delay is not None and delay > 3600 and delay > 2 * max(medians.get('mean_upload_delay_s', 0), 1):
        signals.append(f'Uploaded {delay / 60:.0f} minutes after capture '
                       f'(typical: {medians["mean_upload_delay_s"] / 60:.0f}).')

    accuracy = val('mean_gps_accuracy_m')
    if accuracy is not None and accuracy > 100 and accuracy > 2 * max(medians.get('mean_gps_accuracy_m', 0), 1):
        signals.append(f'Low GPS accuracy ({accuracy:.0f} m).')

    warning_ratio = val('location_warning_ratio')
    if warning_ratio:
        signals.append(f'Off-venue warning on {warning_ratio * 100:.0f}% of captures.')

    prior_ratio = val('prior_rejection_ratio')
    prior_n = val('prior_submissions') or 0
    if prior_ratio is not None and prior_n >= 2 and prior_ratio >= 0.5:
        signals.append(f'{prior_ratio * 100:.0f}% of this student\'s earlier evidence was rejected '
                       f'({int(prior_n)} records).')

    return signals


# =========================================================================== #
# Engagement                                                                  #
# =========================================================================== #

@_decision_support('kmeans')
def engagement(*, scope: AnalyticsScope, user) -> dict:
    """Engagement clusters.

    Fitted on every active student so "HIGH" means the same thing for every
    caller; a Student receives only their own label, staff receive the
    distribution inside their scope, and Event Coordinator/Admin additionally receive the
    per-student labels inside their scope (students they are already
    authorized to see). Faculty receive distribution only.
    """
    population = features.build_student_features(features.all_students())
    result = kmeans_model.cluster_students(population.matrix, weights=features.ENGAGEMENT_WEIGHTS)
    label_by_student = dict(zip(population.student_ids, result.labels))

    base = {
        'available': True,
        'model': 'kmeans',
        'model_version': kmeans_model.KMEANS_MODEL_VERSION,
        'feature_version': features.FEATURE_VERSION,
        'k': result.k,
        'label_order': result.label_order,
        'population': {'n_samples': result.n_samples, 'n_features': result.n_features},
        'centroids': [
            {'label': label, 'engagement_score': round(score, 3),
             'features': dict(zip(features.ENGAGEMENT_FEATURES, [round(float(v), 3) for v in centroid]))}
            for label, score, centroid in zip(result.label_order, result.centroid_scores, result.centroids)
        ],
        'engagement_formula': {
            'description': 'Centroids are ordered by a weighted sum of their feature values in original units.',
            'weights': dict(zip(features.ENGAGEMENT_FEATURES, features.ENGAGEMENT_WEIGHTS.tolist())),
        },
        'note': result.note,
    }

    if scope.is_student:
        own = label_by_student.get(user.id)
        base['own'] = None if own is None else {
            'label': own,
            'features': population.rows.get(user.id, {}),
            'explanation': _engagement_explanation(own, population.rows.get(user.id, {})),
        }
        base['results'] = []
        return base

    scoped_ids = set(_scoped_student_ids(scope))
    scoped_labels = {sid: label_by_student[sid] for sid in scoped_ids if sid in label_by_student}
    distribution = {label: 0 for label in result.label_order}
    for label in scoped_labels.values():
        distribution[label] += 1
    base['distribution'] = distribution
    base['scoped_students'] = len(scoped_labels)

    if scope.is_admin or scope.is_event_coordinator:
        from apps.accounts.models import User
        usernames = dict(User.objects.filter(id__in=scoped_labels).values_list('id', 'username'))
        base['results'] = sorted(
            (
                {'student_id': sid, 'student': usernames.get(sid), 'label': label,
                 'features': population.rows.get(sid, {})}
                for sid, label in scoped_labels.items()
            ),
            key=lambda r: (result.label_order.index(r['label']), r['student'] or ''),
        )
    else:
        base['results'] = []
    return base


def _scoped_student_ids(scope: AnalyticsScope):
    """Students inside the caller's department scope (or all, for Admin)."""
    from apps.accounts.models import User

    queryset = User.objects.filter(role=User.Role.STUDENT, is_active=True)
    if scope.is_admin:
        return queryset.values_list('id', flat=True)
    if scope.department_id is None:
        return []
    return queryset.filter(department_id=scope.department_id).values_list('id', flat=True)


def _engagement_explanation(label, row):
    counts = (
        f"{int(row.get('participations', 0))} participation(s), "
        f"{int(row.get('verified', 0))} verified, "
        f"{int(row.get('attendance_approved', 0))} attendance approval(s), "
        f"{int(row.get('official_achievements', 0))} official achievement(s)"
    )
    return (
        f'Based on your participation history — {counts} — your activity pattern groups with '
        f'students in the {label} engagement cluster. This describes a pattern of counts, not '
        f'an academic judgment.'
    )
