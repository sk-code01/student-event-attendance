"""
Phase 9 §15 — multi-write workflows are atomic, and the two deliberately
non-atomic side channels (notifications, AI) can fail without touching the
decision they describe.
"""

from unittest import mock

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.audit.models import AuditLog
from apps.notifications.models import Notification
from apps.od.models import ODRequest
from apps.registrations.models import Registration
from apps.verification.models import Evidence, EvidenceVerification, EvidenceVersion

from .helpers import AuthMixin, build_universe


class AtomicityTests(AuthMixin, APITestCase):
    """If the audit record — written inside the same transaction as the
    decision — fails, the decision must not survive on its own."""

    def setUp(self):
        self.u = build_universe()
        self.boom = mock.patch('apps.audit.models.AuditLog.record', side_effect=RuntimeError('audit store down'))

    def test_attendance_approval_is_all_or_nothing(self):
        self._auth_as('hoda')
        with self.boom:
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('attendance-approve', args=[self.u.a.attendance.id]))
        attendance = Attendance.objects.get(pk=self.u.a.attendance.pk)
        self.assertEqual(attendance.status, Attendance.Status.PENDING)
        self.assertIsNone(attendance.reviewed_by)

    def test_od_rejection_is_all_or_nothing(self):
        self._auth_as('hoda')
        with self.boom:
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('od-request-reject', args=[self.u.a.od.id]), {'reason': 'no'})
        self.assertEqual(ODRequest.objects.get(pk=self.u.a.od.pk).status, ODRequest.Status.PENDING)

    def test_achievement_approval_is_all_or_nothing(self):
        self._auth_as('hoda')
        with self.boom:
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('achievement-approve', args=[self.u.a.achievement.id]))
        self.assertEqual(Achievement.objects.get(pk=self.u.a.achievement.pk).status,
                         Achievement.Status.PENDING_APPROVAL)

    def test_faculty_decision_is_all_or_nothing(self):
        self.u.b.verification.delete()
        Evidence.objects.filter(pk=self.u.b.evidence.pk).update(status=Evidence.Status.SUBMITTED)
        self._auth_as('facultyb')
        with self.boom:
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('evidence-reject', args=[self.u.b.evidence.id]), {'reason': 'blurry'})
        self.assertEqual(Evidence.objects.get(pk=self.u.b.evidence.pk).status, Evidence.Status.SUBMITTED)
        self.assertFalse(EvidenceVerification.objects.filter(evidence_version=self.u.b.version).exists())

    def test_event_coordinator_override_is_all_or_nothing(self):
        self._auth_as('hoda')
        with self.boom:
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('evidence-override', args=[self.u.a.evidence.id]),
                                 {'decision': 'REJECTED', 'reason': 'override'})
        self.assertEqual(Evidence.objects.get(pk=self.u.a.evidence.pk).status, Evidence.Status.VERIFIED)
        self.assertEqual(EvidenceVerification.objects.filter(evidence_version=self.u.a.version).count(), 1)

    def test_evidence_version_open_is_all_or_nothing(self):
        # Ask for resubmission first so a version 2 is legitimately openable.
        Evidence.objects.filter(pk=self.u.a.evidence.pk).update(status=Evidence.Status.RESUBMISSION_REQUIRED)
        EvidenceVerification.objects.filter(evidence_version=self.u.a.version).update(
            decision=EvidenceVerification.Decision.RESUBMISSION_REQUIRED,
        )
        self._auth_as('studenta')
        with self.boom:
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('evidence-list'), {'participation': self.u.a.participation.id})
        self.assertEqual(EvidenceVersion.objects.filter(evidence=self.u.a.evidence).count(), 1)

    def test_registration_and_its_audit_row_are_written_together(self):
        """Before Phase 9 the registration committed in its own block and the
        audit row was written afterwards, so an audit failure left a
        registration with no trail. Now they are one transaction."""
        self._auth_as('studenta2')
        before = Registration.objects.count()
        with self.boom:
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('registration-list'), {'event': self.u.a.open_event.id})
        self.assertEqual(Registration.objects.count(), before)

    def test_event_lifecycle_writes_are_atomic_with_their_audit_rows(self):
        from apps.events.models import Event
        self._auth_as('hoda')
        draft = self.u.a.draft_event
        with self.boom:
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('event-publish', args=[draft.id]))
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('event-cancel', args=[self.u.a.open_event.id]))
            with self.assertRaises(RuntimeError):
                self.client.patch(reverse('event-detail', args=[draft.id]), {'title': 'Renamed by a failed request'})
            events_before = Event.objects.count()
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('event-list'), {
                    'title': 'Never persisted', 'venue': 'Hall', 'category': 'Technical',
                    'event_date': '2030-01-10', 'conducting_college': self.u.college.id,
                    'registration_start_date': '2030-01-01', 'registration_end_date': '2030-01-05',
                })
        self.assertEqual(Event.objects.get(pk=draft.pk).status, Event.Status.DRAFT)
        self.assertEqual(Event.objects.get(pk=draft.pk).title, draft.title)
        self.assertEqual(Event.objects.get(pk=self.u.a.open_event.pk).status, Event.Status.PUBLISHED)
        self.assertEqual(Event.objects.count(), events_before)

    def test_participation_open_is_atomic_with_its_audit_row(self):
        from apps.participation.models import Participation
        from .helpers import make_registration
        make_registration(student=self.u.a.other_student, event=self.u.a.event)
        self._auth_as('studenta2')
        with self.boom:
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('participation-list'), {'event': self.u.a.event.id})
        self.assertFalse(Participation.objects.filter(student=self.u.a.other_student).exists())


class SideChannelIsolationTests(AuthMixin, APITestCase):
    """Notification and AI failures never roll back or block a decision."""

    def setUp(self):
        self.u = build_universe()

    def _notifications_broken(self):
        return mock.patch('apps.notifications.services.create_notification', side_effect=RuntimeError('mail down'))

    def test_every_decision_survives_a_broken_notification_service(self):
        with self._notifications_broken():
            self._auth_as('hoda')
            approve = reverse('attendance-approve', args=[self.u.a.attendance.id])
            self.assertEqual(self.client.post(approve).status_code, 200)
            self.assertEqual(self.client.post(reverse('od-request-approve', args=[self.u.a.od.id])).status_code, 200)
            approve_achievement = reverse('achievement-approve', args=[self.u.a.achievement.id])
            self.assertEqual(self.client.post(approve_achievement).status_code, 200)
            self.assertEqual(self.client.post(reverse('evidence-override', args=[self.u.a.evidence.id]),
                                              {'decision': 'REJECTED', 'reason': 'override'}).status_code, 200)
            self._auth_as('hodb')
            publish = reverse('event-publish', args=[self.u.b.draft_event.id])
            self.assertEqual(self.client.post(publish).status_code, 200)
            self.assertEqual(self.client.post(reverse('event-cancel', args=[self.u.b.open_event.id])).status_code, 200)
        self.assertEqual(Attendance.objects.get(pk=self.u.a.attendance.pk).status, Attendance.Status.APPROVED)
        self.assertEqual(ODRequest.objects.get(pk=self.u.a.od.pk).status, ODRequest.Status.APPROVED)
        self.assertEqual(Achievement.objects.get(pk=self.u.a.achievement.pk).status, Achievement.Status.APPROVED)
        self.assertEqual(Evidence.objects.get(pk=self.u.a.evidence.pk).status, Evidence.Status.REJECTED)
        # And the audit trail recorded every one of them.
        for action in (
            'ATTENDANCE_APPROVED', 'OD_APPROVED', 'ACHIEVEMENT_APPROVED',
            'EVENT_COORDINATOR_VERIFICATION_OVERRIDE', 'EVENT_PUBLISHED', 'EVENT_CANCELLED',
        ):
            self.assertTrue(AuditLog.objects.filter(action=action).exists(), action)

    def test_notifications_are_only_written_after_the_decision_commits(self):
        """A rolled-back decision produces no notification at all."""
        before = Notification.objects.count()
        self._auth_as('hoda')
        with mock.patch('apps.audit.models.AuditLog.record', side_effect=RuntimeError('audit store down')):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('attendance-approve', args=[self.u.a.attendance.id]))
        self.assertEqual(Notification.objects.count(), before)

    def test_ai_layer_failure_does_not_touch_any_workflow(self):
        broken = RuntimeError('every model is down')
        with mock.patch('ml.recommendation.knn.score_candidates', side_effect=broken), \
             mock.patch('ml.anomaly_detection.isolation_forest.fit_and_score', side_effect=broken), \
             mock.patch('ml.engagement.kmeans.cluster_students', side_effect=broken):
            self._auth_as('hoda')
            approve = reverse('attendance-approve', args=[self.u.a.attendance.id])
            self.assertEqual(self.client.post(approve).status_code, 200)
            self._auth_as('studenta')
            self.assertEqual(self.client.get(reverse('ai-recommendations')).data['available'], False)
            self.assertEqual(self.client.get(reverse('ai-recommendations')).status_code, 200)
