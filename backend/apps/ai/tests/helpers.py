"""
Deterministic AI fixtures (§28).

`build_ai_world()` creates a known universe so every model behaviour can be
asserted exactly rather than "it returned 200":

CS department
  student_high   — 3 participations across 2 categories (Technical x2, Cultural),
                   all verified, 1 attendance approved, 1 official achievement.
  student_mid    — 1 participation (Technical), verified.
  student_low    — 1 live registration, no participation.
  student_cold   — nothing at all (cold-start case).
  Open events (registration open today): cs_tech_open (Technical),
  cs_cultural_open (Cultural), cs_sports_open (Sports).
  Not actionable: cs_cancelled (CANCELLED), cs_closed (window closed),
  cs_registered_by_high (student_high already registered).
EC department
  student_ec     — 1 verified participation on ec_open (Technical).
  ec_open        — open, other department.

Evidence for anomaly detection: five "normal" captures (20 m from venue,
10 m accuracy, 5 s upload delay, one version) and one deliberately unusual one
(5 km from venue, 500 m accuracy, 2 h delay, two versions, off-venue warning).
"""

from datetime import timedelta

from django.utils import timezone

from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.registrations.models import Registration
from apps.verification.models import Evidence, EvidenceCapture, EvidenceVerification, EvidenceVersion
from apps.verification.tests.helpers import (
    make_admin,
    make_college,
    make_department,
    make_event,
    make_faculty,
    make_event_coordinator,
    make_participation,
    make_student,
    make_todays_published_event,
    make_uploaded_image,
    noon_on,
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
    pass


def evidence_with_capture(*, participation, distance_m, accuracy_m, delay_seconds,
                          versions=1, location_warning=False, decision=None, reviewer=None):
    """Submitted evidence with a fully-specified capture, so anomaly features
    are known exactly. Optional Faculty decision."""
    evidence, _ = Evidence.objects.get_or_create(participation=participation)
    version = None
    for n in range(1, versions + 1):
        version = EvidenceVersion.objects.create(
            evidence=evidence, version_number=n, submitted_by=participation.student,
            submitted_at=timezone.now(),
        )
        device_ts = noon_on(participation.event.event_date) - timedelta(seconds=delay_seconds)
        capture = EvidenceCapture.objects.create(
            evidence_version=version, capture_role=EvidenceCapture.Role.PRIMARY,
            object_reference=make_uploaded_image(), mime_type='image/jpeg', file_size=100,
            sha256_hash=f'{participation.id:064x}'[-64:],
            device_capture_timestamp=device_ts, latitude=1, longitude=1,
            gps_accuracy=accuracy_m, venue_distance=distance_m, location_warning=location_warning,
        )
        # server_received_timestamp is auto_now_add; set the delay explicitly.
        EvidenceCapture.objects.filter(pk=capture.pk).update(
            server_received_timestamp=device_ts + timedelta(seconds=delay_seconds),
        )
    evidence.current_version = version
    evidence.status = Evidence.Status.SUBMITTED
    evidence.save(update_fields=['current_version', 'status'])
    participation.status = 'SUBMITTED'
    participation.submitted_at = timezone.now()
    participation.save(update_fields=['status', 'submitted_at'])

    if decision is not None:
        EvidenceVerification.objects.create(
            evidence_version=version, reviewer=reviewer, decision=decision, reason='fixture',
        )
        Evidence.objects.filter(pk=evidence.pk).update(status=decision)
        evidence.refresh_from_db()
    return evidence


def build_ai_world():
    from apps.events.models import Event

    w = World()
    w.college = make_college()
    w.cs = make_department('CS', 'Computer Science')
    w.ec = make_department('EC', 'Electronics')
    w.event_coordinator_cs = make_event_coordinator('hodcs', w.cs)
    w.event_coordinator_ec = make_event_coordinator('hodec', w.ec)
    w.faculty_cs = make_faculty('facultycs', w.cs)
    w.faculty_ec = make_faculty('facultyec', w.ec)
    w.admin = make_admin('sysadmin')

    w.student_high = make_student('studenthigh', w.cs)
    w.student_mid = make_student('studentmid', w.cs)
    w.student_low = make_student('studentlow', w.cs)
    w.student_cold = make_student('studentcold', w.cs)
    w.student_ec = make_student('studentec', w.ec)

    def open_event(title, category, department, days=10):
        e = make_event(
            created_by=(
                w.event_coordinator_cs if department is w.cs
                else w.event_coordinator_ec if department is w.ec
                else w.admin
            ),
            college=w.college, department=department, title=title, status='PUBLISHED',
            days_until_event=days, registration_starts_in=-2, registration_ends_in=min(5, days - 1),
        )
        Event.objects.filter(pk=e.pk).update(category=category)
        e.refresh_from_db()
        return e

    # Past events the students engaged with (today's date so evidence is valid).
    w.cs_tech_past = make_todays_published_event(
        created_by=w.event_coordinator_cs, college=w.college, department=w.cs, title='CS Tech Past',
    )
    Event.objects.filter(pk=w.cs_tech_past.pk).update(category='Technical')
    w.cs_tech_past2 = make_todays_published_event(
        created_by=w.event_coordinator_cs, college=w.college, department=w.cs, title='CS Tech Past 2',
    )
    Event.objects.filter(pk=w.cs_tech_past2.pk).update(category='Technical')
    w.cs_cultural_past = make_todays_published_event(
        created_by=w.event_coordinator_cs, college=w.college, department=w.cs, title='CS Cultural Past',
    )
    Event.objects.filter(pk=w.cs_cultural_past.pk).update(category='Cultural')
    w.ec_past = make_todays_published_event(
        created_by=w.event_coordinator_ec, college=w.college, department=w.ec, title='EC Past',
    )
    Event.objects.filter(pk=w.ec_past.pk).update(category='Technical')
    for e in (w.cs_tech_past, w.cs_tech_past2, w.cs_cultural_past, w.ec_past):
        e.refresh_from_db()

    # Actionable candidates.
    w.cs_tech_open = open_event('CS Tech Open', 'Technical', w.cs)
    w.cs_cultural_open = open_event('CS Cultural Open', 'Cultural', w.cs)
    w.cs_sports_open = open_event('CS Sports Open', 'Sports', w.cs, days=20)
    w.ec_open = open_event('EC Open', 'Technical', w.ec)

    # Not actionable.
    w.cs_cancelled = open_event('CS Cancelled', 'Technical', w.cs)
    Event.objects.filter(pk=w.cs_cancelled.pk).update(status='CANCELLED')
    w.cs_closed = make_event(
        created_by=w.event_coordinator_cs, college=w.college, department=w.cs, title='CS Closed Window',
        status='PUBLISHED', days_until_event=30, registration_starts_in=-20, registration_ends_in=-5,
    )
    Event.objects.filter(pk=w.cs_closed.pk).update(category='Technical')
    w.cs_registered_by_high = open_event('CS Already Registered', 'Technical', w.cs)
    Registration.objects.create(student=w.student_high, event=w.cs_registered_by_high)

    # --- student_high: 3 verified participations, attendance, achievement --
    w.p_high = []
    for event in (w.cs_tech_past, w.cs_tech_past2, w.cs_cultural_past):
        p = make_participation(student=w.student_high, event=event)
        evidence_with_capture(
            participation=p, distance_m=20, accuracy_m=10, delay_seconds=5,
            decision=Decision.VERIFIED, reviewer=w.faculty_cs,
        )
        w.p_high.append(p)
    Attendance.objects.create(
        participation=w.p_high[0], requested_by=w.faculty_cs, status=Attendance.Status.APPROVED,
        reviewed_by=w.event_coordinator_cs, reviewed_at=timezone.now(),
    )
    Achievement.objects.create(
        participation=w.p_high[0], created_by=w.faculty_cs, title='Winner',
        achievement_type='Competition', achievement_date=w.cs_tech_past.event_date,
        status=Achievement.Status.APPROVED, reviewed_by=w.event_coordinator_cs, reviewed_at=timezone.now(),
    )

    # --- student_mid: one verified participation ---------------------------
    w.p_mid = make_participation(student=w.student_mid, event=w.cs_tech_past)
    evidence_with_capture(
        participation=w.p_mid, distance_m=20, accuracy_m=10, delay_seconds=5,
        decision=Decision.VERIFIED, reviewer=w.faculty_cs,
    )

    # --- student_low: registration only -------------------------------------
    Registration.objects.create(student=w.student_low, event=w.cs_tech_past)

    # --- student_ec ----------------------------------------------------------
    w.p_ec = make_participation(student=w.student_ec, event=w.ec_past)
    w.ev_ec = evidence_with_capture(
        participation=w.p_ec, distance_m=20, accuracy_m=10, delay_seconds=5,
        decision=Decision.VERIFIED, reviewer=w.faculty_ec,
    )

    # --- the unusual evidence record (student_mid, second event) -----------
    w.p_unusual = make_participation(student=w.student_mid, event=w.cs_cultural_past)
    w.ev_unusual = evidence_with_capture(
        participation=w.p_unusual, distance_m=5000, accuracy_m=500, delay_seconds=7200,
        versions=2, location_warning=True,
    )
    w.normal_evidence_ids = [
        Evidence.objects.get(participation=p).id for p in (*w.p_high, w.p_mid, w.p_ec)
    ]
    return w
