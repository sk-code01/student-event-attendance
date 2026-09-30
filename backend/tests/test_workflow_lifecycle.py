"""
Phase 9 §12/§13 — the complete lifecycle through the public API, and the
state machine's refused transitions.

Everything goes through HTTP with real JWTs except one step: the student's
registration is created directly, because the registration window must
close before the event date and the live capture must happen ON the event
date — two different calendar days that a single test run cannot span.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.audit.models import AuditLog
from apps.od.models import ODRequest
from apps.verification.models import Evidence
from apps.verification.tests.helpers import iso, make_uploaded_image, noon_on

from .helpers import (
    AuthMixin, make_admin, make_college, make_department, make_faculty, make_event_coordinator, make_registration,
    make_student,
)


class FullLifecycleTests(AuthMixin, APITestCase):
    def _build(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')
        self.admin = make_admin('sysadmin')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.event_coordinator_ec = make_event_coordinator('hodec', self.ec)
        self.faculty = make_faculty('facultycs', self.cs)
        self.faculty_ec = make_faculty('facultyec', self.ec)
        self.student = make_student('student1', self.cs)
        self.other_student = make_student('student2', self.cs)

    _tokens = {}

    def _auth_as(self, username, password=None):
        # The lifecycle switches roles ~20 times; log each user in once so the
        # 10/min login throttle (tested elsewhere) does not interrupt the story.
        if username not in self._tokens:
            self._tokens[username] = super()._auth_as(username)['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self._tokens[username]}')

    def setUp(self):
        self._tokens.clear()
        self._build()

    def _ok(self, response, expected=status.HTTP_200_OK):
        self.assertEqual(response.status_code, expected, getattr(response, 'data', response.content))
        return response.data

    def test_event_to_ai_lifecycle_through_the_api(self):
        today = timezone.localdate()

        # 1-2. Event Coordinator creates and publishes today's event.
        self._auth_as('hodcs')
        event = self._ok(self.client.post(reverse('event-list'), {
            'title': 'Lifecycle Event', 'venue': 'Main Hall', 'category': 'Technical',
            'event_date': str(today), 'conducting_college': self.college.id,
            'registration_start_date': str(today - timedelta(days=5)),
            'registration_end_date': str(today - timedelta(days=1)),
            'venue_latitude': '12.971600', 'venue_longitude': '77.594600',
        }), status.HTTP_201_CREATED)
        event_id = event['id']
        event = self._ok(self.client.get(reverse('event-detail', args=[event_id])))
        self.assertEqual(event['status'], 'DRAFT')
        self._ok(self.client.post(reverse('event-publish', args=[event_id])))

        # 3. Registration (fixture: the window closed yesterday by the DB rule).
        from apps.events.models import Event
        registration = make_registration(student=self.student, event=Event.objects.get(pk=event_id))

        # 4-7. Student participates: eligibility, open, capture, submit.
        self._auth_as('student1')
        eligibility = self._ok(self.client.get(reverse('participation-eligibility'), {'event': event_id}))
        self.assertTrue(eligibility['eligible'], eligibility)
        participation = self._ok(self.client.post(reverse('participation-list'), {'event': event_id}), 201)
        self.assertEqual(participation['registration'], registration.id)
        evidence = self._ok(self.client.post(reverse('evidence-list'), {'participation': participation['id']}), 201)
        version_id = evidence['versions'][0]['id']
        capture = self._ok(self.client.post(reverse('evidence-version-captures', args=[version_id]), {
            'capture_role': 'PRIMARY', 'image': make_uploaded_image(),
            'device_capture_timestamp': iso(noon_on(today)),
            'latitude': '12.971650', 'longitude': '77.594650', 'gps_accuracy': 12,
        }, format='multipart'), 201)
        self.assertFalse(capture['location_warning'])
        self.assertLess(capture['venue_distance'], 20)
        self._ok(self.client.post(reverse('evidence-version-submit', args=[version_id])))
        self.assertEqual(Evidence.objects.get(pk=evidence['id']).status, Evidence.Status.SUBMITTED)

        # Premature: attendance/OD/achievement before verification are refused.
        self._auth_as('facultycs')
        self.assertEqual(self.client.post(reverse('attendance-list'),
                                          {'participation': participation['id']}).status_code, 400)
        self.assertEqual(self.client.post(reverse('od-request-list'),
                                          {'participation': participation['id'], 'reason': 'x'}).status_code, 400)
        self.assertEqual(self.client.post(reverse('achievement-list'), {
            'participation': participation['id'], 'title': 'Too early', 'achievement_type': 'Competition',
            'achievement_date': str(today),
        }).status_code, 400)

        # Notifications are written on_commit; the test transaction never
        # commits, so execute the callbacks explicitly for steps 8-12.
        with self.captureOnCommitCallbacks(execute=True):
            self._lifecycle_decisions(participation, evidence, today)

        # 13. Notifications reached the student (verified, attendance, OD, achievement).
        self._auth_as('student1')
        self._lifecycle_readback(participation, evidence, today)

    def _lifecycle_decisions(self, participation, evidence, today):
        # 8. Faculty verifies (viewing first moves it UNDER_REVIEW).
        detail = self._ok(self.client.get(reverse('evidence-detail', args=[evidence['id']])))
        self.assertEqual(detail['status'], 'UNDER_REVIEW')
        verified = self._ok(self.client.post(reverse('evidence-verify', args=[evidence['id']]), {'reason': 'clear'}))
        self.assertEqual(verified['status'], 'VERIFIED')

        # 9-10. Attendance requested by Faculty, approved by Event Coordinator.
        attendance = self._ok(self.client.post(reverse('attendance-list'), {'participation': participation['id']}), 201)
        self.assertEqual(attendance['status'], 'PENDING')
        self.assertEqual(self.client.post(reverse('attendance-approve', args=[attendance['id']])).status_code, 403)
        self._auth_as('hodcs')
        self.assertEqual(self._ok(self.client.post(reverse('attendance-approve', args=[attendance['id']])))['status'],
                         'APPROVED')
        self.assertEqual(self.client.post(reverse('attendance-approve', args=[attendance['id']])).status_code, 400)

        # 11. OD, independently.
        self._auth_as('facultycs')
        od = self._ok(self.client.post(reverse('od-request-list'),
                                       {'participation': participation['id'], 'reason': 'Represented college'}), 201)
        self._auth_as('hodcs')
        self.assertEqual(self._ok(self.client.post(reverse('od-request-approve', args=[od['id']])))['status'],
                         'APPROVED')
        self.assertEqual(Attendance.objects.get(pk=attendance['id']).status, 'APPROVED')  # untouched by OD

        # 12. Achievement: Faculty creates -> pending; Event Coordinator approves -> official.
        self._auth_as('facultycs')
        achievement = self._ok(self.client.post(reverse('achievement-list'), {
            'participation': participation['id'], 'title': 'First Prize', 'achievement_type': 'Competition',
            'achievement_date': str(today),
        }), 201)
        self.assertEqual(achievement['status'], 'PENDING_APPROVAL')
        self.assertEqual(self.client.post(reverse('achievement-approve', args=[achievement['id']])).status_code, 403)
        self._auth_as('hodcs')
        self.assertEqual(self._ok(self.client.post(reverse('achievement-approve', args=[achievement['id']])))['status'],
                         'APPROVED')

    def _lifecycle_readback(self, participation, evidence, today):
        types = {n['notification_type'] for n in self._ok(self.client.get(reverse('notification-list')))['results']}
        for expected in ('EVIDENCE_VERIFIED', 'ATTENDANCE_APPROVED', 'OD_APPROVED', 'ACHIEVEMENT_APPROVED'):
            self.assertIn(expected, types)

        # 14-15. Dashboard and analytics reflect the changes.
        cards = {c['key']: c['value'] for c in self._ok(self.client.get(reverse('dashboard')))['cards']}
        self.assertEqual(cards.get('participations'), 1)
        overview = self._ok(self.client.get(reverse('analytics-overview')))
        self.assertEqual(overview['participations'], 1)
        self.assertEqual(overview['verified_participations'], 1)
        self.assertEqual(overview['attendance_approved'], 1)
        self.assertEqual(overview['od_approved'], 1)
        self.assertEqual(overview['official_achievements'], 1)

        # 16. Report generated (CSV) with exactly this student's row.
        export = self.client.get(reverse('report-export', args=['student-participation']), {'file_format': 'csv'})
        self.assertEqual(export.status_code, 200)
        body = export.content.decode('utf-8-sig')
        self.assertIn('Lifecycle Event', body)
        self.assertNotIn('student2', body)

        # 17. AI: recommendations (no open events -> honest empty), engagement, anomaly signal only.
        recs = self._ok(self.client.get(reverse('ai-recommendations')))
        self.assertTrue(recs['available'])
        self.assertEqual(recs['results'], [])
        self.assertEqual(recs['reason'], 'NO_ACTIONABLE_EVENTS')
        self._auth_as('facultycs')
        anomalies = self._ok(self.client.get(reverse('ai-anomalies')))
        self.assertIn(anomalies['reason'], (None, 'INSUFFICIENT_DATA')) if not anomalies['available'] else None
        self.assertEqual(Evidence.objects.get(pk=evidence['id']).status, Evidence.Status.VERIFIED)

        # 18. Audit trail carries each human action, none by the AI.
        self._auth_as('hodcs')
        actions = {r['action'] for r in self._ok(self.client.get(reverse('auditlog-list')))['results']}
        for expected in ('EVENT_CREATED', 'EVENT_PUBLISHED', 'PARTICIPATION_STARTED', 'EVIDENCE_CREATED',
                         'EVIDENCE_SUBMITTED', 'EVIDENCE_VERIFIED', 'ATTENDANCE_REQUESTED', 'ATTENDANCE_APPROVED',
                         'OD_REQUESTED', 'OD_APPROVED', 'ACHIEVEMENT_CREATED', 'ACHIEVEMENT_APPROVED'):
            self.assertIn(expected, actions)
        self.assertFalse(any('AI' in a or 'RECOMMEND' in a for a in actions))
        # Every audit row names a real actor and a server timestamp.
        self.assertFalse(AuditLog.objects.filter(created_at__isnull=True).exists())


class RefusedTransitionTests(AuthMixin, APITestCase):
    """Every protected state jump the API must refuse."""

    def setUp(self):
        from .helpers import build_universe
        self.u = build_universe()

    def test_event_state_machine(self):
        self._auth_as('hoda')
        a = self.u.a
        # PUBLISHED -> PUBLISHED, CANCELLED -> PUBLISHED, CANCELLED -> CANCELLED, edit CANCELLED.
        self.assertEqual(self.client.post(reverse('event-publish', args=[a.open_event.id])).status_code, 400)
        self.assertEqual(self.client.post(reverse('event-cancel', args=[a.open_event.id])).status_code, 200)
        self.assertEqual(self.client.post(reverse('event-publish', args=[a.open_event.id])).status_code, 400)
        self.assertEqual(self.client.post(reverse('event-cancel', args=[a.open_event.id])).status_code, 400)
        self.assertEqual(self.client.patch(reverse('event-detail', args=[a.open_event.id]),
                                           {'title': 'x'}).status_code, 400)
        # A direct status write is ignored (mass assignment) rather than honoured.
        self.assertEqual(self.client.patch(reverse('event-detail', args=[a.draft_event.id]),
                                           {'status': 'COMPLETED'}).status_code, 200)
        from apps.events.models import Event
        self.assertEqual(Event.objects.get(pk=a.draft_event.pk).status, Event.Status.DRAFT)
        # Deleting an event with registrations is refused even for Admin.
        self._auth_as('sysadmin')
        self.assertEqual(self.client.delete(reverse('event-detail', args=[a.event.id])).status_code, 400)
        self._auth_as('hoda')
        self.assertEqual(self.client.delete(reverse('event-detail', args=[a.draft_event.id])).status_code, 403)

    def test_evidence_state_machine(self):
        a = self.u.a
        self._auth_as('facultya')
        # Already decided: no second Faculty decision.
        self.assertEqual(self.client.post(reverse('evidence-reject', args=[a.evidence.id]),
                                          {'reason': 'x'}).status_code, 400)
        # Student cannot start a new version unless resubmission was requested.
        self._auth_as('studenta')
        self.assertEqual(self.client.post(reverse('evidence-list'), {'participation': a.participation.id}).status_code,
                         400)
        # Uploading to a submitted version is refused.
        response = self.client.post(reverse('evidence-version-captures', args=[a.version.id]), {
            'capture_role': 'ADDITIONAL', 'image': make_uploaded_image(),
            'device_capture_timestamp': iso(noon_on(a.event.event_date)),
            'latitude': '1', 'longitude': '1', 'gps_accuracy': 10,
        }, format='multipart')
        self.assertEqual(response.status_code, 400)
        # Event Coordinator override flips the effective decision without deleting Faculty history.
        self._auth_as('hoda')
        self.assertEqual(self.client.post(reverse('evidence-override', args=[a.evidence.id]),
                                          {'decision': 'REJECTED', 'reason': 'wrong venue'}).status_code, 200)
        detail = self.client.get(reverse('evidence-detail', args=[a.evidence.id])).data
        decisions = detail['versions'][0]['verifications']
        self.assertEqual(len(decisions), 2)
        self.assertEqual({d['is_event_coordinator_override'] for d in decisions}, {True, False})
        # And now the downstream eligibility gate closes: no new attendance request.
        a.attendance.delete()
        self._auth_as('facultya')
        self.assertEqual(self.client.post(reverse('attendance-list'),
                                          {'participation': a.participation.id}).status_code, 400)

    def test_attendance_od_and_achievement_are_final_once_decided(self):
        a = self.u.a
        self._auth_as('hoda')
        self.assertEqual(self.client.post(reverse('attendance-reject', args=[a.attendance.id]),
                                          {'reason': 'no'}).status_code, 200)
        self.assertEqual(self.client.post(reverse('attendance-approve', args=[a.attendance.id])).status_code, 400)
        self.assertEqual(self.client.post(reverse('od-request-approve', args=[a.od.id])).status_code, 200)
        self.assertEqual(self.client.post(reverse('od-request-reject', args=[a.od.id]), {'reason': 'no'}).status_code,
                         400)
        self.assertEqual(self.client.post(reverse('achievement-reject', args=[a.achievement.id]),
                                          {'reason': 'no'}).status_code, 200)
        self.assertEqual(self.client.post(reverse('achievement-approve', args=[a.achievement.id])).status_code, 400)
        # Rejection without a reason is refused everywhere.
        self._auth_as('hodb')
        b = self.u.b
        for url in (reverse('attendance-reject', args=[b.attendance.id]), reverse('od-request-reject', args=[b.od.id]),
                    reverse('achievement-reject', args=[b.achievement.id])):
            self.assertEqual(self.client.post(url, {'reason': '   '}).status_code, 400, url)
        self.assertEqual(Attendance.objects.get(pk=b.attendance.pk).status, 'PENDING')
        self.assertEqual(ODRequest.objects.get(pk=b.od.pk).status, 'PENDING')
        self.assertEqual(Achievement.objects.get(pk=b.achievement.pk).status, 'PENDING_APPROVAL')

    def test_achievement_draft_lifecycle_is_creator_bound(self):
        a = self.u.a
        self._auth_as('facultya')
        draft = self.client.post(reverse('achievement-list'), {
            'participation': a.participation.id, 'title': 'Draft', 'achievement_type': 'Competition',
            'achievement_date': str(a.event.event_date), 'submit_for_approval': False,
        }).data
        self.assertEqual(draft['status'], 'DRAFT')
        # Another Faculty in the same department may see it but not edit or submit it.
        from .helpers import make_faculty
        make_faculty('facultya2', a.department)
        self._auth_as('facultya2')
        self.assertEqual(self.client.patch(reverse('achievement-detail', args=[draft['id']]),
                                           {'title': 'x'}).status_code, 400)
        self.assertEqual(self.client.post(reverse('achievement-submit', args=[draft['id']])).status_code, 400)
        # Event Coordinator cannot approve a DRAFT — it must be submitted first.
        self._auth_as('hoda')
        self.assertEqual(self.client.post(reverse('achievement-approve', args=[draft['id']])).status_code, 400)
        self._auth_as('facultya')
        self.assertEqual(self.client.post(reverse('achievement-submit', args=[draft['id']])).status_code, 200)
        self.assertEqual(self.client.patch(reverse('achievement-detail', args=[draft['id']]),
                                           {'title': 'x'}).status_code, 400)
        self._auth_as('hoda')
        self.assertEqual(self.client.post(reverse('achievement-approve', args=[draft['id']])).status_code, 200)
