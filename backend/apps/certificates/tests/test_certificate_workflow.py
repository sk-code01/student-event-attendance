"""The certificate rules: upload window, eligibility, attempt limit, Faculty
verification, and the Event Coordinator's post-exhaustion acceptance."""

from datetime import timedelta

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.certificates.models import MAX_CERTIFICATE_ATTEMPTS, Certificate
from apps.certificates.services import submit_certificate
from apps.participation.models import Participation
from apps.participation.tests.helpers import make_todays_published_event
from apps.verification.models import Evidence

from .helpers import (
    make_captured_participation,
    make_college,
    make_department,
    make_event_coordinator,
    make_faculty,
    make_participation,
    make_past_event,
    make_pdf_upload,
    make_student,
)


class CertificateTestBase(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.college = make_college()
        self.coordinator = make_event_coordinator('ec1', self.department)
        self.faculty = make_faculty('fac1', self.department)
        self.student = make_student('stu1', self.department)
        self.event = make_past_event(college=self.college, department=self.department)
        self.participation = make_captured_participation(student=self.student, event=self.event)

    def upload(self, participation=None, file=None):
        return self.client.post(
            reverse('certificate-upload'),
            {'participation': (participation or self.participation).id, 'file': file or make_pdf_upload()},
            format='multipart',
        )

    def reject(self, certificate, reason='Wrong certificate'):
        self.client.force_authenticate(self.faculty)
        response = self.client.post(
            reverse('certificate-decide', args=[certificate.id]),
            {'decision': 'REJECTED', 'reason': reason}, format='json',
        )
        self.client.force_authenticate(self.student)
        return response


class UploadWindowTests(CertificateTestBase):
    def test_upload_is_blocked_on_the_event_day(self):
        todays_event = make_todays_published_event(
            created_by=self.coordinator, college=self.college, department=self.department,
        )
        participation = make_captured_participation(student=self.student, event=todays_event)
        self.client.force_authenticate(self.student)

        response = self.upload(participation=participation)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('midnight', str(response.data).lower())
        self.assertFalse(Certificate.objects.exists())

    def test_upload_opens_the_day_after_the_event(self):
        self.client.force_authenticate(self.student)
        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(Certificate.objects.get().attempt_number, 1)

    def test_eligibility_reports_the_opening_date_while_closed(self):
        todays_event = make_todays_published_event(
            created_by=self.coordinator, college=self.college, department=self.department,
        )
        participation = make_captured_participation(student=self.student, event=todays_event)
        self.client.force_authenticate(self.student)

        response = self.client.get(reverse('certificate-eligibility'), {'participation': participation.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['can_upload'])
        self.assertEqual(
            str(response.data['window_opens_on']),
            str(todays_event.event_date + timedelta(days=1)),
        )

    def test_the_window_stays_open_with_no_expiry_date(self):
        # An event from a year ago is still uploadable: the window closes when
        # a certificate is accepted, not on a deadline.
        old_event = make_past_event(college=self.college, department=self.department, days_ago=365)
        participation = make_captured_participation(student=self.student, event=old_event)
        self.client.force_authenticate(self.student)

        response = self.upload(participation=participation)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)


class CertificateEligibilityTests(CertificateTestBase):
    def test_upload_requires_a_submitted_live_capture(self):
        # A different student: registered for the same past event and past the
        # event date, but who never captured. (The setUp student already has a
        # registration for this event, and a student registers only once.)
        never_captured = make_student('stu3', self.department)
        bare = make_participation(student=never_captured, event=self.event)
        Participation.objects.filter(pk=bare.pk).update(status=Participation.Status.DRAFT)
        bare.refresh_from_db()
        self.client.force_authenticate(never_captured)

        response = self.upload(participation=bare)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('live capture', str(response.data).lower())

    def test_a_rejected_live_capture_does_not_unlock_the_certificate(self):
        Evidence.objects.filter(participation=self.participation).update(status=Evidence.Status.REJECTED)
        self.client.force_authenticate(self.student)

        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_student_cannot_upload_against_another_students_participation(self):
        intruder = make_student('stu2', self.department)
        self.client.force_authenticate(intruder)

        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class AttemptLimitTests(CertificateTestBase):
    def test_three_attempts_are_allowed_and_a_fourth_is_refused(self):
        self.client.force_authenticate(self.student)

        for expected_attempt in range(1, MAX_CERTIFICATE_ATTEMPTS + 1):
            response = self.upload()
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            self.assertEqual(response.data['attempt_number'], expected_attempt)
            self.reject(Certificate.objects.get(attempt_number=expected_attempt, participation=self.participation))

        fourth = self.upload()
        self.assertEqual(fourth.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Certificate.objects.filter(participation=self.participation).count(), 3)

    def test_a_second_upload_is_refused_while_the_first_is_undecided(self):
        self.client.force_authenticate(self.student)
        self.upload()

        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('waiting', str(response.data).lower())

    def test_no_further_upload_once_a_certificate_is_verified(self):
        self.client.force_authenticate(self.student)
        self.upload()
        certificate = Certificate.objects.get()

        self.client.force_authenticate(self.faculty)
        self.client.post(
            reverse('certificate-decide', args=[certificate.id]),
            {'decision': 'VERIFIED'}, format='json',
        )

        self.client.force_authenticate(self.student)
        response = self.upload()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_the_attempt_cap_is_enforced_in_the_service_not_only_the_view(self):
        for _ in range(MAX_CERTIFICATE_ATTEMPTS):
            certificate = submit_certificate(
                participation=self.participation, user=self.student, uploaded_file=make_pdf_upload(),
            )
            certificate.status = Certificate.Status.REJECTED
            certificate.rejection_reason = 'no'
            certificate.save(update_fields=['status', 'rejection_reason'])

        with self.assertRaises(Exception):
            submit_certificate(
                participation=self.participation, user=self.student, uploaded_file=make_pdf_upload(),
            )


class FacultyVerificationTests(CertificateTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.student)
        self.upload()
        self.certificate = Certificate.objects.get()

    def test_faculty_can_verify(self):
        self.client.force_authenticate(self.faculty)
        response = self.client.post(
            reverse('certificate-decide', args=[self.certificate.id]),
            {'decision': 'VERIFIED'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.status, Certificate.Status.VERIFIED)
        self.assertEqual(self.certificate.reviewed_by_id, self.faculty.id)

    def test_rejection_requires_a_reason(self):
        self.client.force_authenticate(self.faculty)
        response = self.client.post(
            reverse('certificate-decide', args=[self.certificate.id]),
            {'decision': 'REJECTED', 'reason': '   '}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.status, Certificate.Status.SUBMITTED)

    def test_the_student_is_told_why_it_was_rejected(self):
        self.reject(self.certificate, reason='The name on the certificate does not match')
        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.rejection_reason, 'The name on the certificate does not match')

    def test_a_student_cannot_decide_their_own_certificate(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(
            reverse('certificate-decide', args=[self.certificate.id]),
            {'decision': 'VERIFIED'}, format='json',
        )
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_faculty_from_another_department_cannot_see_it(self):
        other_department = make_department('EC', 'Electronics')
        outsider = make_faculty('fac2', other_department)
        self.client.force_authenticate(outsider)

        response = self.client.get(reverse('certificate-detail', args=[self.certificate.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_a_decided_certificate_cannot_be_decided_again(self):
        self.client.force_authenticate(self.faculty)
        url = reverse('certificate-decide', args=[self.certificate.id])
        self.client.post(url, {'decision': 'VERIFIED'}, format='json')

        response = self.client.post(url, {'decision': 'REJECTED', 'reason': 'changed my mind'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CoordinatorAcceptanceTests(CertificateTestBase):
    def _exhaust_attempts(self):
        self.client.force_authenticate(self.student)
        for attempt in range(1, MAX_CERTIFICATE_ATTEMPTS + 1):
            self.upload()
            self.reject(Certificate.objects.get(participation=self.participation, attempt_number=attempt))
        return Certificate.objects.get(participation=self.participation, attempt_number=MAX_CERTIFICATE_ATTEMPTS)

    def test_coordinator_can_accept_the_rejected_certificate_after_exhaustion(self):
        certificate = self._exhaust_attempts()
        self.client.force_authenticate(self.coordinator)

        response = self.client.post(reverse('certificate-accept', args=[certificate.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        certificate.refresh_from_db()
        self.assertEqual(certificate.status, Certificate.Status.ACCEPTED_BY_COORDINATOR)
        self.assertEqual(certificate.reviewed_by_id, self.coordinator.id)

    def test_acceptance_is_recorded_in_the_audit_trail(self):
        certificate = self._exhaust_attempts()
        self.client.force_authenticate(self.coordinator)
        self.client.post(reverse('certificate-accept', args=[certificate.id]))

        self.assertTrue(
            AuditLog.objects.filter(
                action='CERTIFICATE_ACCEPTED_AFTER_ATTEMPTS_EXHAUSTED', actor=self.coordinator,
            ).exists(),
        )

    def test_acceptance_is_refused_while_attempts_remain(self):
        self.client.force_authenticate(self.student)
        self.upload()
        certificate = Certificate.objects.get()
        self.reject(certificate)

        self.client.force_authenticate(self.coordinator)
        response = self.client.post(reverse('certificate-accept', args=[certificate.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('remaining', str(response.data).lower())

    def test_faculty_cannot_use_the_acceptance_path(self):
        certificate = self._exhaust_attempts()
        self.client.force_authenticate(self.faculty)

        response = self.client.post(reverse('certificate-accept', args=[certificate.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_a_coordinator_from_another_department_cannot_accept(self):
        certificate = self._exhaust_attempts()
        other_department = make_department('EC', 'Electronics')
        outsider = make_event_coordinator('ec2', other_department)
        self.client.force_authenticate(outsider)

        response = self.client.post(reverse('certificate-accept', args=[certificate.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class CertificateFileAccessTests(CertificateTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.student)
        self.upload()
        self.certificate = Certificate.objects.get()

    def test_the_owner_can_download_it(self):
        response = self.client.get(reverse('certificate-file', args=[self.certificate.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('no-store', response['Cache-Control'])

    def test_faculty_in_the_department_can_download_it(self):
        self.client.force_authenticate(self.faculty)
        response = self.client.get(reverse('certificate-file', args=[self.certificate.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_a_stranger_gets_a_404_rather_than_a_403(self):
        other_department = make_department('EC', 'Electronics')
        outsider = make_student('stu9', other_department)
        self.client.force_authenticate(outsider)

        response = self.client.get(reverse('certificate-file', args=[self.certificate.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_the_storage_path_is_never_exposed(self):
        response = self.client.get(reverse('certificate-detail', args=[self.certificate.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('object_reference', response.data)
        self.assertEqual(response.data['download_url'], f'/api/v1/certificates/{self.certificate.id}/file/')
