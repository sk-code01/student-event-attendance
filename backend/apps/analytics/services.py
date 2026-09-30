"""
Analytics metric computation.

Every number here comes from a single aggregate query over an
already-scoped queryset (see `scope.py`). Nothing iterates a queryset to count
related rows, so query counts stay flat as data grows — asserted by the
query-budget tests.

**Terminology is load-bearing.** Registration, Participation, Verification,
Attendance approval and Achievement are five distinct business concepts and are
never conflated. Where a rate is reported, its denominator is stated in the
response itself (`*_rate_basis`) so the number cannot be read ambiguously.
"""

from django.db.models import Count, F, Q

from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.events.models import Event
from apps.od.models import ODRequest
from apps.registrations.models import Registration
from apps.verification.models import Evidence, EvidenceVerification

from .scope import PENDING_EVIDENCE, AnalyticsScope


def _rate(numerator: int, denominator: int):
    """A percentage, or None when the denominator is zero.

    None rather than 0.0 on purpose: "no attendance requests were made" and
    "every request was refused" are different facts, and reporting both as 0%
    would invent data. The frontend renders None as an em dash.
    """
    if not denominator:
        return None
    return round(numerator * 100.0 / denominator, 2)


# ---------------------------------------------------------------- overview --

def overview(scope: AnalyticsScope) -> dict:
    """Headline counts for whatever the caller is allowed to see."""
    registrations = scope.registrations().aggregate(
        total=Count('id'),
        live=Count('id', filter=Q(status=Registration.Status.REGISTERED)),
        cancelled=Count('id', filter=Q(status=Registration.Status.CANCELLED)),
    )
    participations_total = scope.participations().count()
    evidence = scope.evidence().aggregate(
        total=Count('id'),
        verified=Count('id', filter=Q(status=Evidence.Status.VERIFIED)),
        pending=Count('id', filter=PENDING_EVIDENCE),
    )
    attendance = scope.attendance().aggregate(
        total=Count('id'),
        approved=Count('id', filter=Q(status=Attendance.Status.APPROVED)),
    )
    od = scope.od_requests().aggregate(
        total=Count('id'),
        approved=Count('id', filter=Q(status=ODRequest.Status.APPROVED)),
    )
    achievements = scope.achievements().aggregate(
        total=Count('id'),
        approved=Count('id', filter=Q(status=Achievement.Status.APPROVED)),
    )

    return {
        'events': scope.events().count(),
        'registrations': registrations['total'],
        'live_registrations': registrations['live'],
        'participations': participations_total,
        'evidence_submitted': evidence['total'],
        'verified_participations': evidence['verified'],
        'pending_verification': evidence['pending'],
        'attendance_requests': attendance['total'],
        'attendance_approved': attendance['approved'],
        'od_requests': od['total'],
        'od_approved': od['approved'],
        'achievements': achievements['total'],
        'official_achievements': achievements['approved'],
        # Participations per live registration. Stated explicitly rather than
        # left to the reader, because a "participation rate" with an unstated
        # denominator is not a defensible metric.
        'participation_rate': _rate(participations_total, registrations['live']),
        'participation_rate_basis': 'participations / live (non-cancelled) registrations, within scope',
    }


# ----------------------------------------------------------- participation --

def participation(scope: AnalyticsScope) -> dict:
    registrations = scope.registrations().aggregate(
        total=Count('id'),
        live=Count('id', filter=Q(status=Registration.Status.REGISTERED)),
    )
    participations = scope.participations().aggregate(
        total=Count('id'),
        submitted=Count('id', filter=Q(status='SUBMITTED')),
        draft=Count('id', filter=Q(status='DRAFT')),
    )
    evidence = scope.evidence().aggregate(
        verified=Count('id', filter=Q(status=Evidence.Status.VERIFIED)),
        pending=Count('id', filter=PENDING_EVIDENCE),
        rejected=Count('id', filter=Q(status=Evidence.Status.REJECTED)),
        resubmission=Count('id', filter=Q(status=Evidence.Status.RESUBMISSION_REQUIRED)),
    )

    by_event = list(
        scope.participations()
        # `event_id` is a real column on Participation, so select it directly;
        # aliasing it via F('event__id') collides with the model field.
        .values('event_id', event_title=F('event__title'))
        .annotate(participations=Count('id'))
        .order_by('-participations', 'event_title')[:25]
    )
    by_category = list(
        scope.participations()
        .values(category=F('event__category'))
        .annotate(participations=Count('id'))
        .order_by('-participations', 'category')[:25]
    )

    return {
        'total_registrations': registrations['total'],
        'live_registrations': registrations['live'],
        'total_participations': participations['total'],
        'submitted_participations': participations['submitted'],
        'draft_participations': participations['draft'],
        'verified_participations': evidence['verified'],
        'pending_verification': evidence['pending'],
        'rejected_evidence': evidence['rejected'],
        'resubmission_required': evidence['resubmission'],
        'participation_rate': _rate(participations['total'], registrations['live']),
        'participation_rate_basis': 'participations / live (non-cancelled) registrations, within scope',
        'verification_success_rate': _rate(evidence['verified'], participations['submitted']),
        'verification_success_rate_basis': 'verified evidence / submitted participations, within scope',
        'by_event': by_event,
        'by_category': by_category,
    }


# ------------------------------------------------------------------ events --

def events(scope: AnalyticsScope) -> dict:
    """Event lifecycle counts.

    `COMPLETED` is a real persisted status maintained by
    `Event.objects.mark_past_events_completed()`; it is read here, never
    re-derived, so analytics cannot disagree with the events API.
    """
    Event.objects.mark_past_events_completed()

    queryset = scope.events()
    lifecycle = queryset.aggregate(
        total=Count('id'),
        draft=Count('id', filter=Q(status=Event.Status.DRAFT)),
        published=Count('id', filter=Q(status=Event.Status.PUBLISHED)),
        cancelled=Count('id', filter=Q(status=Event.Status.CANCELLED)),
        completed=Count('id', filter=Q(status=Event.Status.COMPLETED)),
    )
    by_category = list(
        queryset.values('category').annotate(events=Count('id')).order_by('-events', 'category')[:25]
    )

    # One grouped query for per-event engagement rather than a count per
    # event. The annotations are named *_count because Event's reverse
    # accessors are already called `registrations`/`participations`, and an
    # annotation may not shadow a model field; the public keys are mapped back
    # below over at most 25 already-fetched rows, so this is not an N+1.
    annotated = queryset.annotate(
        registration_count=Count('registrations', distinct=True),
        participation_count=Count('participations', distinct=True),
    ).order_by('-event_date', 'title')[:25]
    per_event = [
        {
            'id': e.id, 'title': e.title, 'event_date': e.event_date,
            'category': e.category, 'status': e.status,
            'registrations': e.registration_count,
            'participations': e.participation_count,
        }
        for e in annotated
    ]

    return {
        'total_events': lifecycle['total'],
        'draft_events': lifecycle['draft'],
        'published_events': lifecycle['published'],
        'cancelled_events': lifecycle['cancelled'],
        'completed_events': lifecycle['completed'],
        'by_category': by_category,
        'per_event': per_event,
    }


# ----------------------------------------------------------- registrations --

def registrations(scope: AnalyticsScope) -> dict:
    queryset = scope.registrations()
    totals = queryset.aggregate(
        total=Count('id'),
        live=Count('id', filter=Q(status=Registration.Status.REGISTERED)),
        cancelled=Count('id', filter=Q(status=Registration.Status.CANCELLED)),
    )
    by_event = list(
        # `event_id` is a real column on Registration — select, do not alias.
        queryset.values('event_id', event_title=F('event__title'))
        .annotate(registrations=Count('id'))
        .order_by('-registrations', 'event_title')[:25]
    )
    return {
        'total_registrations': totals['total'],
        'live_registrations': totals['live'],
        'cancelled_registrations': totals['cancelled'],
        'cancellation_rate': _rate(totals['cancelled'], totals['total']),
        'cancellation_rate_basis': 'cancelled registrations / all registrations, within scope',
        'by_event': by_event,
    }


# -------------------------------------------------------------- attendance --

def attendance(scope: AnalyticsScope) -> dict:
    """Attendance only. OD is a separate workflow and is never folded in here."""
    queryset = scope.attendance()
    totals = queryset.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status=Attendance.Status.PENDING)),
        approved=Count('id', filter=Q(status=Attendance.Status.APPROVED)),
        rejected=Count('id', filter=Q(status=Attendance.Status.REJECTED)),
    )
    decided = totals['approved'] + totals['rejected']
    by_event = list(
        queryset.values(
            event_id=F('participation__event__id'), event_title=F('participation__event__title'),
        )
        .annotate(
            requests=Count('id'),
            approved=Count('id', filter=Q(status=Attendance.Status.APPROVED)),
        )
        .order_by('-requests', 'event_title')[:25]
    )
    return {
        'total_requests': totals['total'],
        'pending': totals['pending'],
        'approved': totals['approved'],
        'rejected': totals['rejected'],
        'approval_rate': _rate(totals['approved'], decided),
        'approval_rate_basis': 'approved / decided (approved + rejected) requests; pending excluded',
        'by_event': by_event,
    }


# ---------------------------------------------------------------------- od --

def od(scope: AnalyticsScope) -> dict:
    """OD only — independent of attendance, never a status of it."""
    queryset = scope.od_requests()
    totals = queryset.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status=ODRequest.Status.PENDING)),
        approved=Count('id', filter=Q(status=ODRequest.Status.APPROVED)),
        rejected=Count('id', filter=Q(status=ODRequest.Status.REJECTED)),
    )
    decided = totals['approved'] + totals['rejected']
    by_event = list(
        queryset.values(
            event_id=F('participation__event__id'), event_title=F('participation__event__title'),
        )
        .annotate(
            requests=Count('id'),
            approved=Count('id', filter=Q(status=ODRequest.Status.APPROVED)),
        )
        .order_by('-requests', 'event_title')[:25]
    )
    return {
        'total_requests': totals['total'],
        'pending': totals['pending'],
        'approved': totals['approved'],
        'rejected': totals['rejected'],
        'approval_rate': _rate(totals['approved'], decided),
        'approval_rate_basis': 'approved / decided (approved + rejected) requests; pending excluded',
        'by_event': by_event,
    }


# ------------------------------------------------------------ achievements --

def achievements(scope: AnalyticsScope) -> dict:
    """Only APPROVED achievements are official. A verified participation never
    becomes an achievement on its own, so these counts are not derivable from
    participation figures."""
    queryset = scope.achievements()
    totals = queryset.aggregate(
        total=Count('id'),
        draft=Count('id', filter=Q(status=Achievement.Status.DRAFT)),
        pending=Count('id', filter=Q(status=Achievement.Status.PENDING_APPROVAL)),
        approved=Count('id', filter=Q(status=Achievement.Status.APPROVED)),
        rejected=Count('id', filter=Q(status=Achievement.Status.REJECTED)),
    )
    decided = totals['approved'] + totals['rejected']
    by_type = list(
        queryset.values('achievement_type')
        .annotate(achievements=Count('id'),
                  approved=Count('id', filter=Q(status=Achievement.Status.APPROVED)))
        .order_by('-achievements', 'achievement_type')[:25]
    )
    by_event = list(
        queryset.values(
            event_id=F('participation__event__id'), event_title=F('participation__event__title'),
        )
        .annotate(achievements=Count('id'))
        .order_by('-achievements', 'event_title')[:25]
    )
    return {
        'total_achievements': totals['total'],
        'draft': totals['draft'],
        'pending_approval': totals['pending'],
        'official_achievements': totals['approved'],
        'rejected': totals['rejected'],
        'approval_rate': _rate(totals['approved'], decided),
        'approval_rate_basis': 'approved / decided (approved + rejected) achievements; drafts and pending excluded',
        'by_type': by_type,
        'by_event': by_event,
    }


# ------------------------------------------------------------ verification --

def verification(scope: AnalyticsScope) -> dict:
    """Verification outcomes by **effective** decision.

    `Evidence.status` is the denormalised effective decision: both
    `record_faculty_decision` and `record_event_coordinator_override` write it, and an Event Coordinator
    override overwrites it. Aggregating on it therefore counts the decision
    that actually governs, not a superseded Faculty one — which is the
    behaviour the phase brief requires. Calling
    `EvidenceVersion.effective_verification` per row instead would be an N+1
    and would produce the same answer; `test_event_coordinator_override_flips_the_effective_outcome`
    pins the invariant so a future change to the service layer cannot silently
    break it.

    Override activity is reported separately so the human review history stays
    visible rather than being hidden behind its own outcome.
    """
    queryset = scope.evidence()
    totals = queryset.aggregate(
        total=Count('id'),
        pending=Count('id', filter=PENDING_EVIDENCE),
        verified=Count('id', filter=Q(status=Evidence.Status.VERIFIED)),
        rejected=Count('id', filter=Q(status=Evidence.Status.REJECTED)),
        resubmission=Count('id', filter=Q(status=Evidence.Status.RESUBMISSION_REQUIRED)),
    )
    decided = totals['verified'] + totals['rejected'] + totals['resubmission']

    overrides = EvidenceVerification.objects.filter(
        is_event_coordinator_override=True,
        evidence_version__evidence__in=queryset.values('id'),
    ).count()

    by_event = list(
        queryset.values(
            event_id=F('participation__event__id'), event_title=F('participation__event__title'),
        )
        .annotate(
            submissions=Count('id'),
            verified=Count('id', filter=Q(status=Evidence.Status.VERIFIED)),
            rejected=Count('id', filter=Q(status=Evidence.Status.REJECTED)),
        )
        .order_by('-submissions', 'event_title')[:25]
    )

    return {
        'total_evidence': totals['total'],
        'pending_review': totals['pending'],
        'verified': totals['verified'],
        'rejected': totals['rejected'],
        'resubmission_required': totals['resubmission'],
        'event_coordinator_overrides': overrides,
        'verification_rate': _rate(totals['verified'], decided),
        'verification_rate_basis': 'verified / decided evidence by effective decision; pending excluded',
        'decision_basis': 'effective decision (Event Coordinator override takes precedence over the Faculty decision)',
        'by_event': by_event,
    }


# -------------------------------------------------------------- departments --

def departments(scope: AnalyticsScope) -> dict:
    """Department comparison — Admin sees every department, an Event Coordinator sees only
    their own. Students and Faculty never reach this endpoint (the view
    refuses them), so no unrestricted comparison is ever returned.

    Department-less (Admin-created) events are **not** attributed to any
    department; they are reported separately for Admin so the totals still
    reconcile without inventing an owner.
    """
    rows = list(
        scope.participations()
        .filter(event__department__isnull=False)
        .values(department_id=F('event__department__id'), department=F('event__department__name'))
        .annotate(participations=Count('id'))
        .order_by('department')
    )
    registration_rows = {
        row['department_id']: row['registrations']
        for row in scope.registrations()
        .filter(event__department__isnull=False)
        .values(department_id=F('event__department__id'))
        .annotate(registrations=Count('id'))
    }
    attendance_rows = {
        row['department_id']: row['approved']
        for row in scope.attendance()
        .filter(participation__event__department__isnull=False)
        .values(department_id=F('participation__event__department__id'))
        .annotate(approved=Count('id', filter=Q(status=Attendance.Status.APPROVED)))
    }
    od_rows = {
        row['department_id']: row['approved']
        for row in scope.od_requests()
        .filter(participation__event__department__isnull=False)
        .values(department_id=F('participation__event__department__id'))
        .annotate(approved=Count('id', filter=Q(status=ODRequest.Status.APPROVED)))
    }
    achievement_rows = {
        row['department_id']: row['approved']
        for row in scope.achievements()
        .filter(participation__event__department__isnull=False)
        .values(department_id=F('participation__event__department__id'))
        .annotate(approved=Count('id', filter=Q(status=Achievement.Status.APPROVED)))
    }
    event_rows = {
        # `department_id` is a real column on Event, so it is selected
        # directly — aliasing it via F('department__id') would collide with
        # the model field and raise.
        row['department_id']: row['events']
        for row in scope.events()
        .filter(department__isnull=False)
        .values('department_id')
        .annotate(events=Count('id'))
    }

    for row in rows:
        did = row['department_id']
        row['registrations'] = registration_rows.get(did, 0)
        row['attendance_approved'] = attendance_rows.get(did, 0)
        row['od_approved'] = od_rows.get(did, 0)
        row['official_achievements'] = achievement_rows.get(did, 0)
        row['events'] = event_rows.get(did, 0)

    # Departments with events but no participations yet still deserve a row.
    seen = {row['department_id'] for row in rows}
    for did, count in event_rows.items():
        if did not in seen:
            rows.append({
                'department_id': did,
                'department': _department_name(did),
                'participations': 0,
                'registrations': registration_rows.get(did, 0),
                'attendance_approved': attendance_rows.get(did, 0),
                'od_approved': od_rows.get(did, 0),
                'official_achievements': achievement_rows.get(did, 0),
                'events': count,
            })
    rows.sort(key=lambda r: (r['department'] or ''))

    unassigned = scope.events().filter(department__isnull=True).count() if scope.is_admin else 0

    return {
        'departments': rows,
        'department_less_events': unassigned,
        'department_less_note': (
            'Admin-created events belong to no department and are counted here rather than '
            'being attributed to one.'
        ),
    }


def _department_name(department_id):
    from apps.departments.models import Department
    department = Department.objects.filter(pk=department_id).only('name').first()
    return department.name if department else None
