from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import RegistrationRequest

from .helpers import make_admin, make_department, make_event_coordinator, make_student

User = get_user_model()


class RegistrationWorkflowTests(APITestCase):
    def setUp(self):
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')
        self.event_coordinator_cs = make_event_coordinator('hodcs', self.cs)
        self.event_coordinator_ec = make_event_coordinator('hodec', self.ec)
        self.admin = make_admin('siteadmin')

        self.applicant = make_student('applicant1', self.cs, is_active=False)
        self.registration_request = RegistrationRequest.objects.create(
            user=self.applicant, role=User.Role.STUDENT, department=self.cs,
        )

    def _login(self, username, password='StrongPass123!'):
        response = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': password})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data['access']

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_event_coordinator_sees_only_own_department_requests(self):
        self._auth(self._login('hodcs'))
        response = self.client.get(reverse('registration-request-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = [item['user']['username'] for item in response.data['results']]
        self.assertIn('applicant1', usernames)

        self._auth(self._login('hodec'))
        response = self.client.get(reverse('registration-request-list'))
        usernames = [item['user']['username'] for item in response.data['results']]
        self.assertNotIn('applicant1', usernames)

    def test_admin_sees_all_departments_requests(self):
        self._auth(self._login('siteadmin'))
        response = self.client.get(reverse('registration-request-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = [item['user']['username'] for item in response.data['results']]
        self.assertIn('applicant1', usernames)

    def test_event_coordinator_can_approve_own_department_request(self):
        self._auth(self._login('hodcs'))
        url = reverse('registration-request-approve', args=[self.registration_request.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.applicant.refresh_from_db()
        self.assertTrue(self.applicant.is_active)

        self.registration_request.refresh_from_db()
        self.assertEqual(self.registration_request.status, RegistrationRequest.Status.APPROVED)
        self.assertEqual(self.registration_request.reviewed_by_id, self.event_coordinator_cs.id)

    def test_event_coordinator_cannot_approve_other_department_request(self):
        self._auth(self._login('hodec'))
        url = reverse('registration-request-approve', args=[self.registration_request.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.applicant.refresh_from_db()
        self.assertFalse(self.applicant.is_active)

    def test_event_coordinator_can_reject_with_reason(self):
        self._auth(self._login('hodcs'))
        url = reverse('registration-request-reject', args=[self.registration_request.id])
        response = self.client.post(url, {'rejection_reason': 'Invalid student ID proof.'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.registration_request.refresh_from_db()
        self.assertEqual(self.registration_request.status, RegistrationRequest.Status.REJECTED)
        self.assertEqual(self.registration_request.rejection_reason, 'Invalid student ID proof.')

        self.applicant.refresh_from_db()
        self.assertFalse(self.applicant.is_active)

    def test_rejection_without_reason_is_rejected(self):
        self._auth(self._login('hodcs'))
        url = reverse('registration-request-reject', args=[self.registration_request.id])
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_already_reviewed_request_cannot_be_reviewed_again(self):
        self._auth(self._login('hodcs'))
        approve_url = reverse('registration-request-approve', args=[self.registration_request.id])
        self.client.post(approve_url)

        second_response = self.client.post(approve_url)
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_approve_any_department_request(self):
        self._auth(self._login('siteadmin'))
        url = reverse('registration-request-approve', args=[self.registration_request.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_student_cannot_access_registration_request_list(self):
        make_student('activestudent', self.cs, is_active=True)
        self._auth(self._login('activestudent'))
        response = self.client.get(reverse('registration-request-list'))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_access_registration_request_list(self):
        response = self.client.get(reverse('registration-request-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rejected_account_gets_distinct_login_message(self):
        self._auth(self._login('hodcs'))
        reject_url = reverse('registration-request-reject', args=[self.registration_request.id])
        self.client.post(reject_url, {'rejection_reason': 'Not eligible.'})
        self.client.credentials()

        login_response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'applicant1', 'password': 'StrongPass123!',
        })
        self.assertEqual(login_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('rejected', str(login_response.data).lower())


class RegistrationStatusTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.applicant = make_student('pendingapplicant', self.department, is_active=False)
        RegistrationRequest.objects.create(user=self.applicant, role=User.Role.STUDENT, department=self.department)

    def test_pending_applicant_can_check_status_without_logging_in(self):
        response = self.client.post(reverse('registration-status'), {'username': 'pendingapplicant'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], RegistrationRequest.Status.PENDING)

    def test_unknown_username_returns_404(self):
        response = self.client.post(reverse('registration-status'), {'username': 'nobodyhere'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
