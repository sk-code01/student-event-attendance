"""
Feature engineering: the only place the AI layer touches the ORM.

Each builder returns plain numpy arrays plus the row identities needed to map
scores back to records. No password, token, storage key, file path, raw image
or face data is ever read here — the models see counts, distances, durations
and categories, nothing else.

**Temporal status of every feature is stated**, because the anomaly model in
particular must not "predict" a decision using information created by that
same decision:

  * PRE-VERIFICATION — known before any Faculty decision on this record.
  * HISTORICAL       — derived from the student's *earlier* records, using only
                       decisions made before this record was created.
  * OUTCOME          — a decision on this record. Never used as an anomaly
                       input; used only in engagement counts, where it is the
                       thing being measured rather than predicted.

Every aggregate here is a grouped query, never a per-row loop with a query
inside, so the feature builders stay flat as data grows.
"""

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from django.db.models import Avg, Count, Max, Q
from django.utils import timezone

from apps.accounts.models import User
from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.events.models import Event
from apps.od.models import ODRequest
from apps.participation.models import Participation
from apps.registrations.models import Registration
from apps.verification.models import Evidence, EvidenceCapture

FEATURE_VERSION = 'features-v1'


# =========================================================================== #
# Recommendation                                                              #
# =========================================================================== #

# How much each block of the event vector counts toward distance. Category is
# the strongest signal a student's history carries; the others refine it.
CATEGORY_WEIGHT = 1.0
DEPARTMENT_WEIGHT = 0.6
POPULARITY_WEIGHT = 0.4
RECENCY_WEIGHT = 0.3

RECENCY_HORIZON_DAYS = 90  # events further out than this all look equally "not soon"


@dataclass
class EventVectors:
    categories: list                     # one-hot vocabulary, in column order
    history_events: list                 # Event rows the student engaged with
    history: np.ndarray                  # (n_history, d)
    candidate_events: list               # actionable Event rows
    candidates: np.ndarray               # (n_candidates, d)
    popularity: dict = field(default_factory=dict)   # event_id -> live registration count
    max_popularity: int = 0


def student_history_events(student):
    """Events this student has engaged with: any participation, or any live
    registration. Cancelled registrations are excluded — they are a signal of
    *disengagement* and must not teach the model that the student likes that
    kind of event."""
    participated = Event.objects.filter(participations__student=student)
    registered = Event.objects.filter(
        registrations__student=student, registrations__status=Registration.Status.REGISTERED,
    )
    return list((participated | registered).distinct().order_by('id'))


def candidate_events(student, *, today=None):
    """Events the student can actually act on right now.

    Mirrors `apps.registrations.serializers.RegistrationCreateSerializer`
    exactly: PUBLISHED, inside the registration window. Additionally excludes
    every event the student already has *any* registration row for — including
    cancelled ones, because the `(student, event)` unique constraint means a
    cancelled registration can never be re-registered, so recommending it
    would be recommending something impossible.
    """
    today = today or timezone.localdate()
    already = Registration.objects.filter(student=student).values('event_id')
    return list(
        Event.objects.filter(
            status=Event.Status.PUBLISHED,
            registration_start_date__lte=today,
            registration_end_date__gte=today,
        )
        .exclude(id__in=already)
        .select_related('department')
        .order_by('event_date', 'id')
    )


def build_event_vectors(student, *, today=None) -> EventVectors:
    """Feature vectors for the student's history and for every candidate, on
    a common basis so KNN distance is meaningful.

    Vector layout: [one-hot category ...] + [department match] + [popularity]
    + [recency]. All values are in [0, 1] before weighting, so no single block
    dominates by unit alone.

    Data-leakage guard: history is *what the student has done*, candidates are
    *what is open today*. Nothing about a candidate's future outcome is used.
    """
    today = today or timezone.localdate()
    history_events = student_history_events(student)
    candidates = candidate_events(student, today=today)

    all_events = history_events + candidates
    categories = sorted({(e.category or '').strip().lower() for e in all_events})
    category_index = {c: i for i, c in enumerate(categories)}

    # One grouped query for popularity across every event involved.
    popularity = {
        row['event_id']: row['live']
        for row in Registration.objects.filter(
            event_id__in=[e.id for e in all_events], status=Registration.Status.REGISTERED,
        ).values('event_id').annotate(live=Count('id'))
    }
    max_popularity = max(popularity.values(), default=0)

    def vector(event) -> np.ndarray:
        cat = np.zeros(len(categories))
        key = (event.category or '').strip().lower()
        if key in category_index:
            cat[category_index[key]] = CATEGORY_WEIGHT

        department_match = 1.0 if (
            event.department_id is not None and event.department_id == student.department_id
        ) else 0.0

        pop = (popularity.get(event.id, 0) / max_popularity) if max_popularity else 0.0

        days = (event.event_date - today).days
        recency = 1.0 - min(max(days, 0), RECENCY_HORIZON_DAYS) / RECENCY_HORIZON_DAYS

        return np.concatenate([
            cat,
            [department_match * DEPARTMENT_WEIGHT, pop * POPULARITY_WEIGHT, recency * RECENCY_WEIGHT],
        ])

    width = len(categories) + 3
    history = np.array([vector(e) for e in history_events]) if history_events else np.zeros((0, width))
    cands = np.array([vector(e) for e in candidates]) if candidates else np.zeros((0, width))

    return EventVectors(
        categories=categories,
        history_events=history_events,
        history=history,
        candidate_events=candidates,
        candidates=cands,
        popularity=popularity,
        max_popularity=max_popularity,
    )


# =========================================================================== #
# Anomaly                                                                     #
# =========================================================================== #

ANOMALY_FEATURES = [
    # name,                    temporal status
    ('capture_count',          'PRE-VERIFICATION'),  # captures on the current version
    ('version_count',          'HISTORICAL'),        # resubmissions on this evidence
    ('max_venue_distance_m',   'PRE-VERIFICATION'),
    ('mean_venue_distance_m',  'PRE-VERIFICATION'),
    ('mean_gps_accuracy_m',    'PRE-VERIFICATION'),
    ('mean_upload_delay_s',    'PRE-VERIFICATION'),  # server receipt minus device capture
    ('location_warning_ratio', 'PRE-VERIFICATION'),
    ('prior_submissions',      'HISTORICAL'),        # this student's earlier evidence
    ('prior_rejection_ratio',  'HISTORICAL'),        # decided BEFORE this record was created
]
ANOMALY_FEATURE_NAMES = [name for name, _ in ANOMALY_FEATURES]


@dataclass
class EvidenceFeatures:
    evidence_ids: list
    matrix: np.ndarray            # (n_evidence, len(ANOMALY_FEATURE_NAMES))
    rows: dict                    # evidence_id -> {feature_name: value}
    population_medians: dict      # feature_name -> median, for human-readable signals


def build_evidence_features(evidence_queryset) -> EvidenceFeatures:
    """Features for every evidence record in `evidence_queryset`.

    Three grouped queries regardless of how many records exist:
      1. capture statistics per current version,
      2. version counts per evidence,
      3. the student's prior evidence outcomes, with a temporal guard so only
         decisions made *before* each record's creation count as "prior".
    """
    evidence_rows = list(
        evidence_queryset.select_related('participation', 'current_version')
        .values('id', 'created_at', 'current_version_id', 'participation__student_id')
        .order_by('id')
    )
    if not evidence_rows:
        return EvidenceFeatures([], np.zeros((0, len(ANOMALY_FEATURE_NAMES))), {}, {})

    evidence_ids = [row['id'] for row in evidence_rows]
    version_ids = [row['current_version_id'] for row in evidence_rows if row['current_version_id']]

    # 1. Capture statistics per current version.
    capture_stats = {
        row['evidence_version_id']: row
        for row in EvidenceCapture.objects.filter(evidence_version_id__in=version_ids)
        .values('evidence_version_id')
        .annotate(
            capture_count=Count('id'),
            max_distance=Max('venue_distance'),
            mean_distance=Avg('venue_distance'),
            mean_accuracy=Avg('gps_accuracy'),
            warning_count=Count('id', filter=Q(location_warning=True)),
        )
    }
    # Upload delay is computed from the two timestamps per capture; a grouped
    # Avg over a DurationField expression is unreliable across backends, so
    # the (small) per-version capture list is fetched once and reduced here.
    delays = defaultdict(list)
    for version_id, device_ts, server_ts in EvidenceCapture.objects.filter(
        evidence_version_id__in=version_ids,
    ).values_list('evidence_version_id', 'device_capture_timestamp', 'server_received_timestamp'):
        if device_ts and server_ts:
            delays[version_id].append(max((server_ts - device_ts).total_seconds(), 0.0))

    # 2. Version count per evidence.
    version_counts = {
        row['id']: row['n']
        for row in Evidence.objects.filter(id__in=evidence_ids).values('id').annotate(n=Count('versions'))
    }

    # 3. Prior history per student: every decided evidence with its decision
    # time, so each record only sees decisions made before it was created.
    student_ids = {row['participation__student_id'] for row in evidence_rows}
    prior_by_student = defaultdict(list)
    for eid, student_id, created_at, status in Evidence.objects.filter(
        participation__student_id__in=student_ids,
    ).exclude(status__in=[Evidence.Status.SUBMITTED, Evidence.Status.UNDER_REVIEW]) \
     .values_list('id', 'participation__student_id', 'updated_at', 'status'):
        prior_by_student[student_id].append((eid, created_at, status))

    rows = {}
    matrix = []
    for row in evidence_rows:
        stats = capture_stats.get(row['current_version_id'], {})
        capture_count = stats.get('capture_count', 0) or 0
        delay_list = delays.get(row['current_version_id'], [])

        priors = [
            (eid, decided_at, status)
            for eid, decided_at, status in prior_by_student.get(row['participation__student_id'], [])
            if eid != row['id'] and decided_at is not None and decided_at < row['created_at']
        ]
        prior_rejected = sum(1 for _, _, s in priors if s == Evidence.Status.REJECTED)

        values = {
            'capture_count': float(capture_count),
            'version_count': float(version_counts.get(row['id'], 1) or 1),
            'max_venue_distance_m': _f(stats.get('max_distance')),
            'mean_venue_distance_m': _f(stats.get('mean_distance')),
            'mean_gps_accuracy_m': _f(stats.get('mean_accuracy')),
            'mean_upload_delay_s': float(np.mean(delay_list)) if delay_list else np.nan,
            'location_warning_ratio': (stats.get('warning_count', 0) / capture_count) if capture_count else 0.0,
            'prior_submissions': float(len(priors)),
            'prior_rejection_ratio': (prior_rejected / len(priors)) if priors else 0.0,
        }
        rows[row['id']] = values
        matrix.append([values[name] for name in ANOMALY_FEATURE_NAMES])

    matrix = np.array(matrix, dtype=float)
    medians = {
        name: float(np.nanmedian(matrix[:, i])) if not np.all(np.isnan(matrix[:, i])) else 0.0
        for i, name in enumerate(ANOMALY_FEATURE_NAMES)
    }
    return EvidenceFeatures(evidence_ids, matrix, rows, medians)


def _f(value):
    return float(value) if value is not None else np.nan


# =========================================================================== #
# Engagement                                                                  #
# =========================================================================== #

ENGAGEMENT_FEATURES = [
    'registrations', 'participations', 'verified', 'attendance_approved',
    'od_approved', 'official_achievements', 'category_diversity', 'recency_score',
]

# The documented engagement formula used to ORDER K-Means centroids into
# LOW / MODERATE / HIGH. Weights are in original units: one verified
# participation is worth three registrations, an official achievement three,
# and so on. Recency is a 0-1 score (1 = participated recently), weighted so it
# can nudge but never dominate the counts.
ENGAGEMENT_WEIGHTS = np.array([1.0, 3.0, 3.0, 2.0, 1.0, 3.0, 1.0, 2.0])

RECENCY_WINDOW_DAYS = 180


@dataclass
class StudentFeatures:
    student_ids: list
    matrix: np.ndarray            # (n_students, len(ENGAGEMENT_FEATURES))
    rows: dict                    # student_id -> {feature: value}


def build_student_features(student_queryset) -> StudentFeatures:
    """Engagement features for every student in `student_queryset`.

    Seven grouped queries total, one per source table, then a merge in Python
    over at most a few hundred students — never a per-student query.
    """
    student_ids = list(student_queryset.values_list('id', flat=True).order_by('id'))
    if not student_ids:
        return StudentFeatures([], np.zeros((0, len(ENGAGEMENT_FEATURES))), {})

    def grouped(queryset, key, **annotations):
        return {row[key]: row for row in queryset.values(key).annotate(**annotations)}

    registrations = grouped(
        Registration.objects.filter(student_id__in=student_ids, status=Registration.Status.REGISTERED),
        'student_id', n=Count('id'),
    )
    participations = grouped(
        Participation.objects.filter(student_id__in=student_ids),
        'student_id', n=Count('id'), last=Max('created_at'),
        diversity=Count('event__category', distinct=True),
    )
    verified = grouped(
        Evidence.objects.filter(participation__student_id__in=student_ids, status=Evidence.Status.VERIFIED),
        'participation__student_id', n=Count('id'),
    )
    attendance = grouped(
        # Through the registration: attendance is keyed there, and a record
        # marked for a student who never captured has no participation.
        Attendance.objects.filter(
            registration__student_id__in=student_ids, status=Attendance.Status.APPROVED,
        ),
        'registration__student_id', n=Count('id'),
    )
    od = grouped(
        ODRequest.objects.filter(participation__student_id__in=student_ids, status=ODRequest.Status.APPROVED),
        'participation__student_id', n=Count('id'),
    )
    achievements = grouped(
        Achievement.objects.filter(
            participation__student_id__in=student_ids, status=Achievement.Status.APPROVED,
        ),
        'participation__student_id', n=Count('id'),
    )

    now = timezone.now()
    rows = {}
    matrix = []
    for sid in student_ids:
        p = participations.get(sid, {})
        last = p.get('last')
        if last is None:
            recency = 0.0
        else:
            age_days = (now - last).total_seconds() / 86400.0
            recency = max(0.0, 1.0 - min(age_days, RECENCY_WINDOW_DAYS) / RECENCY_WINDOW_DAYS)

        values = {
            'registrations': float(registrations.get(sid, {}).get('n', 0)),
            'participations': float(p.get('n', 0)),
            'verified': float(verified.get(sid, {}).get('n', 0)),
            'attendance_approved': float(attendance.get(sid, {}).get('n', 0)),
            'od_approved': float(od.get(sid, {}).get('n', 0)),
            'official_achievements': float(achievements.get(sid, {}).get('n', 0)),
            'category_diversity': float(p.get('diversity', 0)),
            'recency_score': recency,
        }
        rows[sid] = values
        matrix.append([values[name] for name in ENGAGEMENT_FEATURES])

    return StudentFeatures(student_ids, np.array(matrix, dtype=float), rows)


def all_students():
    """The clustering population: every active student system-wide.

    The model is fitted on the whole population so a label means the same
    thing regardless of who asks; callers then return only the rows inside
    their own scope. The feature matrix carries no identities.
    """
    return User.objects.filter(role=User.Role.STUDENT, is_active=True)
