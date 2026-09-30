"""The Event Coordinator's final decision on a verified certificate (§23)."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.certificates.models import MAX_CERTIFICATE_ATTEMPTS, Certificate, FinalDecision
from apps.notifications.models import Notification

from .helpers import (
    make_captured_participation,
    make_college,
    make_department,
    make_event_coordinator,
    make_faculty,
    make_past_event,
    make_pdf_upload,
    make_student,
)


class FinalDecisionTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.college = make_college()
        self.coordinator = make_event_coordinator('ec1', self.department)
        self.faculty = make_faculty('fac1', self.department)
        self.student = make_student('stu1', self.department)
        self.event = make_past_event(college=self.college, department=self.department)
        self.participation = make_captured_participation(student=self.student, event=self.event)

        self.client.force_authenticate(self.student)
        self.client.post(
            reverse('certificate-upload'),
            {'participation': self.participation.id, 'file': make_pdf_upload()},
            format='multipart',
        )
        self.certificate = Certificate.objects.get()

    def _faculty_verifies(self):
        self.client.force_authenticate(self.faculty)
        response = self.client.post(
            reverse('certificate-decide', args=[self.certificate.id]),
            {'decision': 'VERIFIED'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.certificate.refresh_from_db()

    def _final(self, decision, reason=''):
        self.client.force_authenticate(self.coordinator)
        body = {'decision': decision}
        if reason:
            body['reason'] = reason
        return self.client.post(
            reverse('certificate-final-decision', args=[self.certificate.id]), body, format='json',
        )

    def test_the_coordinator_accepts_a_verified_certificate(self):
        self._faculty_verifies()
        response = self._final(FinalDecision.ACCEPTED)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.final_decision, FinalDecision.ACCEPTED)
        self.assertEqual(self.certificate.final_decided_by_id, self.coordinator.id)
        # The Faculty decision is still readable underneath it.
        self.assertEqual(self.certificate.status, Certificate.Status.VERIFIED)
        self.assertEqual(self.certificate.reviewed_by_id, self.faculty.id)

    def test_a_final_rejection_requires_a_reason(self):
        self._faculty_verifies()
        response = self._final(FinalDecision.REJECTED)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.final_decision, '')

    def test_a_final_rejection_records_its_reason(self):
        self._faculty_verifies()
        response = self._final(FinalDecision.REJECTED, reason='Certificate is for a different event')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.final_rejection_reason, 'Certificate is for a different event')

    def test_the_student_is_notified_of_the_final_decision(self):
        self._faculty_verifies()
        # Notifications are deliberately deferred to transaction commit, so a
        # decision that rolls back never notifies. The test transaction never
        # commits, so the callbacks are run explicitly here.
        with self.captureOnCommitCallbacks(execute=True):
            self._final(FinalDecision.REJECTED, reason='Wrong event')

        notification = Notification.objects.filter(
            recipient=self.student, related_entity_type='certificate',
        ).order_by('-id').first()
        self.assertIsNotNone(notification)
        self.assertIn('Wrong event', notification.message)

    def test_it_cannot_be_decided_before_faculty_verify_it(self):
        # Requirement 23 puts the coordinator after verification, not instead
        # of it.
        response = self._final(FinalDecision.ACCEPTED)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('verified', str(response.data).lower())

    def test_a_rejected_certificate_never_reaches_the_final_stage(self):
        self.client.force_authenticate(self.faculty)
        self.client.post(
            reverse('certificate-decide', args=[self.certificate.id]),
            {'decision': 'REJECTED', 'reason': 'Illegible'}, format='json',
        )
        response = self._final(FinalDecision.ACCEPTED)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_final_decision_cannot_be_changed(self):
        self._faculty_verifies()
        self._final(FinalDecision.ACCEPTED)

        response = self._final(FinalDecision.REJECTED, reason='changed my mind')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.final_decision, FinalDecision.ACCEPTED)

    def test_a_final_rejection_grants_no_extra_attempt(self):
        self._faculty_verifies()
        self._final(FinalDecision.REJECTED, reason='Wrong event')

        # The attempt limit is governed by the Faculty decisions alone;
        # rejecting here must not quietly hand out a fourth attempt.
        self.client.force_authenticate(self.student)
        response = self.client.post(
            reverse('certificate-upload'),
            {'participation': self.participation.id, 'file': make_pdf_upload()},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertLessEqual(
            Certificate.objects.filter(participation=self.participation).count(),
            MAX_CERTIFICATE_ATTEMPTS,
        )

    def test_faculty_cannot_make_the_final_decision(self):
        self._faculty_verifies()
        self.client.force_authenticate(self.faculty)
        response = self.client.post(
            reverse('certificate-final-decision', args=[self.certificate.id]),
            {'decision': FinalDecision.ACCEPTED}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_the_student_cannot_make_the_final_decision(self):
        self._faculty_verifies()
        self.client.force_authenticate(self.student)
        response = self.client.post(
            reverse('certificate-final-decision', args=[self.certificate.id]),
            {'decision': FinalDecision.ACCEPTED}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_coordinator_from_another_department_cannot_decide(self):
        self._faculty_verifies()
        other_department = make_department('EC', 'Electronics')
        outsider = make_event_coordinator('ec2', other_department)

        self.client.force_authenticate(outsider)
        response = self.client.post(
            reverse('certificate-final-decision', args=[self.certificate.id]),
            {'decision': FinalDecision.ACCEPTED}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_decision_is_recorded_in_the_audit_trail(self):
        self._faculty_verifies()
        self._final(FinalDecision.ACCEPTED)

        self.assertTrue(
            AuditLog.objects.filter(
                action='CERTIFICATE_FINAL_ACCEPTED', actor=self.coordinator,
            ).exists(),
        )

    def test_the_record_reports_that_it_awaits_a_final_decision(self):
        self._faculty_verifies()
        self.client.force_authenticate(self.coordinator)
        response = self.client.get(reverse('certificate-detail', args=[self.certificate.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['awaits_final_decision'])
