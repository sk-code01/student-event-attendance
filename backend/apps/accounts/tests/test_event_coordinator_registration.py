"""Event Coordinator role, self-registration, and the new identity fields.

Covers the rules that replaced the HOD role: the role itself no longer
exists, a department has at most one active Event Coordinator, an Event
Coordinator registers themselves without an approval step, and Student and
Faculty registrations now carry an institution-issued identifier that must be
unique.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import RegistrationRequest

from .helpers import make_department, make_event_coordinator, make_faculty, make_student

User = get_user_model()


class RoleTests(APITestCase):
    def test_hod_role_no_longer_exists(self):
        self.assertFalse(hasattr(User.Role, 'HOD'))
        self.assertNotIn('HOD', [value for value, _ in User.Role.choices])

    def test_event_coordinator_role_exists_with_a_readable_label(self):
        self.assertEqual(User.Role.EVENT_COORDINATOR.value, 'EVENT_COORDINATOR')
        self.assertEqual(User.Role.EVENT_COORDINATOR.label, 'Event Coordinator')


class OneEventCoordinatorPerDepartmentTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')

    def test_a_second_active_coordinator_is_refused_by_the_database(self):
        make_event_coordinator('ec1', self.department)
        # Not merely a serializer rule: the partial unique index is what holds
        # when two registrations race each other.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_event_coordinator('ec2', self.department)

    def test_an_inactive_coordinator_does_not_block_a_replacement(self):
        outgoing = make_event_coordinator('ec1', self.department)
        outgoing.is_active = False
        outgoing.save(update_fields=['is_active'])

        replacement = make_event_coordinator('ec2', self.department)
        self.assertTrue(replacement.is_active)

    def test_each_department_gets_its_own_coordinator(self):
        other = make_department('EC', 'Electronics')
        make_event_coordinator('ec1', self.department)
        make_event_coordinator('ec2', other)
        self.assertEqual(User.objects.filter(role=User.Role.EVENT_COORDINATOR).count(), 2)


class EventCoordinatorSelfRegistrationTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.url = reverse('auth-register')

    def _payload(self, **overrides):
        payload = {
            'username': 'coordinator1',
            'email': 'coordinator1@example.com',
            'full_name': 'Asha Rao',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
            'role': User.Role.EVENT_COORDINATOR,
            'department': self.department.id,
            # An Event Coordinator is a faculty member, so they are issued —
            # and must supply — the college's Faculty ID.
            'faculty_id': 'FAC-EC-001',
        }
        payload.update(overrides)
        return payload

    def test_registration_activates_the_account_immediately(self):
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        user = User.objects.get(username='coordinator1')
        self.assertTrue(user.is_active)
        self.assertEqual(user.role, User.Role.EVENT_COORDINATOR)
        self.assertEqual(user.full_name, 'Asha Rao')

    def test_no_approval_request_is_created(self):
        self.client.post(self.url, self._payload())
        user = User.objects.get(username='coordinator1')
        # There is nobody above a coordinator in the department to approve it,
        # so a pending request would never be actioned.
        self.assertFalse(RegistrationRequest.objects.filter(user=user).exists())

    def test_the_response_does_not_tell_them_to_wait_for_approval(self):
        response = self.client.post(self.url, self._payload())
        self.assertNotIn('pending', response.data['detail'].lower())

    def test_a_second_coordinator_for_the_same_department_is_rejected(self):
        make_event_coordinator('existing', self.department)

        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('department', response.data)
        self.assertFalse(User.objects.filter(username='coordinator1').exists())

    def test_a_coordinator_must_supply_a_faculty_id(self):
        response = self.client.post(self.url, self._payload(faculty_id=''))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('faculty_id', response.data)
        self.assertFalse(User.objects.filter(username='coordinator1').exists())

    def test_a_coordinator_may_not_supply_a_university_registration_number(self):
        # That identifier belongs to students. Supplying it is a sign the
        # caller has the wrong idea about the role, so it is refused rather
        # than quietly dropped.
        response = self.client.post(self.url, self._payload(
            university_registration_number='1AY22MC001',
        ))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('university_registration_number', response.data)

    def test_the_faculty_id_is_stored_and_normalised(self):
        # Submitted upper, stored lower: the direction matters because the
        # identifier is shown back to people, and two spellings of one id
        # would read as two identifiers.
        response = self.client.post(self.url, self._payload(faculty_id='FAC-EC-777'))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        user = User.objects.get(username='coordinator1')
        self.assertEqual(user.faculty_id, 'fac-ec-777')
        self.assertIsNone(user.university_registration_number)

    def test_a_faculty_id_already_held_by_a_faculty_member_is_refused(self):
        # The point of checking uniqueness across roles rather than within
        # one: an Event Coordinator *is* a faculty member, so the same
        # identifier must not yield two identities by switching role.
        make_faculty('existingfaculty', self.department, faculty_id='FAC-EC-001')

        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('faculty_id', response.data)
        self.assertFalse(User.objects.filter(username='coordinator1').exists())

    def test_the_database_refuses_a_coordinator_sharing_a_faculty_id(self):
        # The serializer is not the only thing holding this: a data import or
        # a future endpoint would hit the unique index instead.
        make_faculty('existingfaculty', self.department, faculty_id='FAC-EC-555')
        other = make_department('EC', 'Electronics')

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create(
                    username='coordinator2', email='coordinator2@example.com',
                    role=User.Role.EVENT_COORDINATOR, department=other,
                    faculty_id='FAC-EC-555', is_active=True,
                )


class StudentIdentityFieldTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.url = reverse('auth-register')

    def _payload(self, **overrides):
        payload = {
            'username': 'student1',
            'email': 'student1@example.com',
            'full_name': 'Ravi Kumar',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
            'role': User.Role.STUDENT,
            'department': self.department.id,
            'university_registration_number': '1AY22MC045',
        }
        payload.update(overrides)
        return payload

    def test_full_name_is_required(self):
        response = self.client.post(self.url, self._payload(full_name=''))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('full_name', response.data)

    def test_registration_number_is_required(self):
        response = self.client.post(self.url, self._payload(university_registration_number=''))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('university_registration_number', response.data)

    def test_registration_number_is_unique(self):
        self.client.post(self.url, self._payload())
        response = self.client.post(self.url, self._payload(
            username='student2', email='student2@example.com',
        ))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('university_registration_number', response.data)

    def test_registration_number_uniqueness_ignores_case(self):
        self.client.post(self.url, self._payload())
        response = self.client.post(self.url, self._payload(
            username='student2', email='student2@example.com',
            university_registration_number='1ay22mc045',
        ))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_any_institution_format_is_accepted(self):
        # A USN, a UUCMS number and a plain serial have different shapes; none
        # of them may be rejected for not matching some assumed pattern.
        for index, number in enumerate(('1AY22MC045', 'U03CS21S0123', '2021-CS-0456')):
            response = self.client.post(self.url, self._payload(
                username=f'formats{index}', email=f'formats{index}@example.com',
                university_registration_number=number,
            ))
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_a_student_may_not_supply_a_faculty_id(self):
        response = self.client.post(self.url, self._payload(faculty_id='FAC-9'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_the_approval_workflow_is_unchanged(self):
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        user = User.objects.get(username='student1')
        self.assertFalse(user.is_active)
        self.assertEqual(
            RegistrationRequest.objects.get(user=user).status,
            RegistrationRequest.Status.PENDING,
        )


class FacultyIdentityFieldTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.url = reverse('auth-register')

    def _payload(self, **overrides):
        payload = {
            'username': 'faculty1',
            'email': 'faculty1@example.com',
            'full_name': 'Meera Iyer',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
            'role': User.Role.FACULTY,
            'department': self.department.id,
            'faculty_id': 'FAC-1024',
        }
        payload.update(overrides)
        return payload

    def test_full_name_is_required(self):
        response = self.client.post(self.url, self._payload(full_name='   '))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('full_name', response.data)

    def test_faculty_id_is_required(self):
        response = self.client.post(self.url, self._payload(faculty_id=''))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('faculty_id', response.data)

    def test_faculty_id_is_unique(self):
        self.client.post(self.url, self._payload())
        response = self.client.post(self.url, self._payload(
            username='faculty2', email='faculty2@example.com',
        ))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('faculty_id', response.data)

    def test_the_approval_workflow_is_unchanged(self):
        self.client.post(self.url, self._payload())
        user = User.objects.get(username='faculty1')
        self.assertFalse(user.is_active)
        self.assertEqual(
            RegistrationRequest.objects.get(user=user).status,
            RegistrationRequest.Status.PENDING,
        )


class IdentifierBelongsToItsRoleTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')

    def test_a_student_cannot_be_given_a_faculty_id(self):
        student = make_student('s1', self.department)
        student.faculty_id = 'FAC-1'
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                student.save(update_fields=['faculty_id'])

    def test_a_coordinator_cannot_be_given_a_registration_number(self):
        coordinator = make_event_coordinator('ec1', self.department)
        coordinator.university_registration_number = '1AY22MC001'
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                coordinator.save(update_fields=['university_registration_number'])
