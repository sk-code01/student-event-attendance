from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import RegistrationRequest

from .helpers import make_department, make_student

User = get_user_model()


class RegistrationTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.url = reverse('auth-register')

    def _payload(self, **overrides):
        payload = {
            'username': 'newstudent',
            'email': 'newstudent@example.com',
            'full_name': 'New Student',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
            'role': User.Role.STUDENT,
            'department': self.department.id,
            'university_registration_number': '1AY22MC001',
        }
        payload.update(overrides)
        return payload

    def test_successful_registration_creates_inactive_user_and_pending_request(self):
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        user = User.objects.get(username='newstudent')
        self.assertFalse(user.is_active)
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertEqual(user.department_id, self.department.id)

        registration_request = RegistrationRequest.objects.get(user=user)
        self.assertEqual(registration_request.status, RegistrationRequest.Status.PENDING)

    def test_faculty_role_is_accepted(self):
        response = self.client.post(self.url, self._payload(
            username='newfaculty', email='newfaculty@example.com', role=User.Role.FACULTY,
            university_registration_number='', faculty_id='FAC-001',
        ))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(User.objects.get(username='newfaculty').role, User.Role.FACULTY)

    def test_event_coordinator_registers_itself_and_is_active_at_once(self):
        # This replaced the old rule that the role could not self-register:
        # an Event Coordinator has no approver above them in the department,
        # so the account is usable immediately. The one-per-department limit
        # is what constrains it instead — see
        # test_event_coordinator_registration.py.
        response = self.client.post(self.url, self._payload(
            role=User.Role.EVENT_COORDINATOR, university_registration_number='',
            faculty_id='FAC-EC-001',
        ))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        user = User.objects.get(username='newstudent')
        self.assertEqual(user.role, User.Role.EVENT_COORDINATOR)
        self.assertTrue(user.is_active)
        self.assertFalse(RegistrationRequest.objects.filter(user=user).exists())

    def test_admin_role_is_rejected_from_public_registration(self):
        response = self.client.post(self.url, self._payload(role=User.Role.ADMIN))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('role', response.data)

    def test_duplicate_username_is_rejected(self):
        make_student('newstudent', self.department)
        response = self.client.post(self.url, self._payload(email='different@example.com'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_duplicate_email_is_rejected(self):
        make_student('existing', self.department, password='StrongPass123!')
        User.objects.filter(username='existing').update(email='taken@example.com')
        response = self.client.post(self.url, self._payload(email='taken@example.com'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_password_mismatch_is_rejected(self):
        response = self.client.post(self.url, self._payload(confirm_password='Different123!'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirm_password', response.data)

    def test_weak_password_is_rejected(self):
        response = self.client.post(self.url, self._payload(password='12345678', confirm_password='12345678'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_username_with_uppercase_or_symbols_is_rejected(self):
        response = self.client.post(self.url, self._payload(username='Bad-User'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)

    def test_invalid_department_is_rejected(self):
        response = self.client.post(self.url, self._payload(department=999999))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('department', response.data)

    def test_inactive_department_is_not_selectable(self):
        inactive_dept = make_department('OLD', 'Retired Department', is_active=False)
        response = self.client.post(self.url, self._payload(department=inactive_dept.id))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('department', response.data)

    def test_pending_account_cannot_login(self):
        self.client.post(self.url, self._payload())
        login_response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'newstudent', 'password': 'StrongPass123!',
        })
        self.assertEqual(login_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('pending', str(login_response.data).lower())
