"""
Deterministic analytics fixtures.

`build_world()` creates a known universe whose every aggregate is worked out by
hand in the docstring, so the tests assert exact numbers rather than merely
HTTP 200. Two departments exist so cross-department isolation is testable, and
the fixture deliberately includes the awkward cases: a cancelled registration,
a cancelled event, rejected evidence, an Event Coordinator override that flips an outcome, a
rejected attendance, a rejected OD, a pending achievement and a department-less
Admin event.
"""


from django.utils import timezone

from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.od.models import ODRequest
from apps.registrations.models import Registration
from apps.verification.models import Evidence, EvidenceVerification
from apps.verification.tests.helpers import (
    make_admin,
    make_college,
    make_department,
    make_event,
    make_faculty,
    make_event_coordinator,
    make_participation,
    make_student,
    make_submitted_evidence,
    make_todays_published_event,
)

DEFAULT_PASSWORD = 'StrongPass123!'
Decision = EvidenceVerification.Decision


class AuthMixin:
    def _auth_as(self, username):
        from django.urls import reverse
        from rest_framework import status

        login = self.client.post(
            reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD},
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')


class World:
    """Namespace for the fixture objects, so tests can reach any of them."""


def _decide(evidence, reviewer, decision, reason='because', override_by=None, override_decision=None):
    version = evidence.current_version
    EvidenceVerification.objects.create(
        evidence_version=version, reviewer=reviewer, decision=decision,
        reason=reason, is_event_coordinator_override=False,
    )
    effective = decision
    if override_by is not None:
        EvidenceVerification.objects.create(
            evidence_version=version, reviewer=override_by, decision=override_decision,
            reason='reviewed personally', is_event_coordinator_override=True,
        )
        effective = override_decision
    Evidence.objects.filter(pk=evidence.pk).update(status=effective)
    evidence.refresh_from_db()
    return evidence


def build_world():
    """Builds the fixture.

    **CS department (the department under test)**

    Events: ``cs_event`` (today, PUBLISHED) and ``cs_cancelled`` (CANCELLED).

    ``student_a`` — 3 registrations (2 live, 1 cancelled), 2 participations:
      * ``p_a1`` evidence VERIFIED by Faculty -> attendance APPROVED, OD APPROVED,
        1 achievement APPROVED
      * ``p_a2`` evidence REJECTED by Faculty
    ``student_b`` — 1 registration, 1 participation ``p_b1`` whose evidence the
      Faculty VERIFIED but the Event Coordinator then overrode to REJECTED, so its effective
      decision is REJECTED. Attendance REJECTED, OD PENDING, achievement
      PENDING_APPROVAL.
    ``student_c`` — 1 registration, no participation.

    So within CS: registrations 5 (4 live, 1 cancelled), participations 3,
    evidence 3 (verified 1, rejected 2 by effective decision), attendance 2
    (1 approved, 1 rejected), OD 2 (1 approved, 1 pending), achievements 2
    (1 approved, 1 pending).

    **EC department** — one event, one student, one participation with VERIFIED
    evidence and an APPROVED attendance. Nothing in CS may ever count it.

    **Admin** — one department-less event with one registration, which belongs
    to no department and must never be attributed to one.
    """
    w = World()
    w.college = make_college()
    w.cs = make_department('CS', 'Computer Science')
    w.ec = make_department('EC', 'Electronics')

    w.event_coordinator_cs = make_event_coordinator('hodcs', w.cs)
    w.event_coordinator_ec = make_event_coordinator('hodec', w.ec)
    w.faculty_cs = make_faculty('facultycs', w.cs)
    w.faculty_ec = make_faculty('facultyec', w.ec)
    w.admin = make_admin('sysadmin')

    w.student_a = make_student('studenta', w.cs)
    w.student_b = make_student('studentb', w.cs)
    w.student_c = make_student('studentc', w.cs)
    w.student_ec = make_student('studentec', w.ec)

    w.cs_event = make_todays_published_event(
        created_by=w.event_coordinator_cs, college=w.college, department=w.cs, title='CS Event',
    )
    # registration_ends_in must stay below days_until_event: the Phase 2
    # CheckConstraint `registration_end_before_event_date` rejects a window
    # that closes after the event, and make_event's default (5) would exceed
    # this event's 3-day horizon.
    w.cs_cancelled = make_event(
        created_by=w.event_coordinator_cs, college=w.college, department=w.cs, title='CS Cancelled',
        status='CANCELLED', days_until_event=3, registration_starts_in=-2, registration_ends_in=1,
    )
    w.ec_event = make_todays_published_event(
        created_by=w.event_coordinator_ec, college=w.college, department=w.ec, title='EC Event',
    )
    # Admin-created: belongs to no department at all.
    w.orphan_event = make_todays_published_event(
        created_by=w.admin, college=w.college, department=None, title='Orphan Event',
    )

    # --- student_a -------------------------------------------------------
    w.p_a1 = make_participation(student=w.student_a, event=w.cs_event)
    w.ev_a1, _ = make_submitted_evidence(participation=w.p_a1)
    _decide(w.ev_a1, w.faculty_cs, Decision.VERIFIED, 'looks good')

    w.p_a2 = make_participation(student=w.student_a, event=w.cs_cancelled)
    w.ev_a2, _ = make_submitted_evidence(participation=w.p_a2)
    _decide(w.ev_a2, w.faculty_cs, Decision.REJECTED, 'blurry')

    # A third, cancelled registration with no participation.
    w.cancelled_registration = Registration.objects.create(
        student=w.student_a, event=w.orphan_event, status=Registration.Status.CANCELLED,
        cancelled_at=timezone.now(),
    )

    w.att_a1 = Attendance.objects.create(
        participation=w.p_a1, requested_by=w.faculty_cs, status=Attendance.Status.APPROVED,
        reviewed_by=w.event_coordinator_cs, reviewed_at=timezone.now(),
    )
    w.od_a1 = ODRequest.objects.create(
        participation=w.p_a1, requested_by=w.faculty_cs, reason='Inter-college fest',
        status=ODRequest.Status.APPROVED, reviewed_by=w.event_coordinator_cs, reviewed_at=timezone.now(),
    )
    w.ach_a1 = Achievement.objects.create(
        participation=w.p_a1, created_by=w.faculty_cs, title='First Place',
        achievement_type='Competition', achievement_date=w.cs_event.event_date,
        status=Achievement.Status.APPROVED, reviewed_by=w.event_coordinator_cs, reviewed_at=timezone.now(),
    )

    # --- student_b: the Event Coordinator override case --------------------------------
    w.p_b1 = make_participation(student=w.student_b, event=w.cs_event)
    w.ev_b1, _ = make_submitted_evidence(participation=w.p_b1)
    _decide(
        w.ev_b1, w.faculty_cs, Decision.VERIFIED, 'faculty said yes',
        override_by=w.event_coordinator_cs, override_decision=Decision.REJECTED,
    )
    w.att_b1 = Attendance.objects.create(
        participation=w.p_b1, requested_by=w.faculty_cs, status=Attendance.Status.REJECTED,
        reviewed_by=w.event_coordinator_cs, reviewed_at=timezone.now(), rejection_reason='evidence overridden',
    )
    w.od_b1 = ODRequest.objects.create(
        participation=w.p_b1, requested_by=w.faculty_cs, reason='conference',
    )
    w.ach_b1 = Achievement.objects.create(
        participation=w.p_b1, created_by=w.faculty_cs, title='Runner Up',
        achievement_type='Competition', achievement_date=w.cs_event.event_date,
        status=Achievement.Status.PENDING_APPROVAL,
    )

    # --- student_c: registered only ---------------------------------------
    Registration.objects.create(student=w.student_c, event=w.cs_event)

    # --- EC department, must never appear in CS numbers -------------------
    w.p_ec = make_participation(student=w.student_ec, event=w.ec_event)
    w.ev_ec, _ = make_submitted_evidence(participation=w.p_ec)
    _decide(w.ev_ec, w.faculty_ec, Decision.VERIFIED)
    w.att_ec = Attendance.objects.create(
        participation=w.p_ec, requested_by=w.faculty_ec, status=Attendance.Status.APPROVED,
        reviewed_by=w.event_coordinator_ec, reviewed_at=timezone.now(),
    )

    return w
