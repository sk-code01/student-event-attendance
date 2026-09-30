"""The backend, not the Angular form, decides which identifier a role needs.

Every case here calls the API directly with a payload the registration form
would never produce. The form is a convenience; if it were the only thing
enforcing these rules, anyone with curl could create a Student with no
university registration number, or a Faculty member carrying a student's.

The rule being enforced: a Student is issued a university registration number,
both faculty roles are issued the college's Faculty ID, and nobody carries the
identifier belonging to the other side.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import make_department, make_faculty, make_student

User = get_user_model()

# Both faculty roles, exercised identically: an Event Coordinator is a faculty
# member, so any rule that holds for one must hold for the other. Writing them
# as a table rather than as separate methods is what makes a future divergence
# between the two visible instead of silently untested.
FACULTY_ROLES = (User.Role.FACULTY, User.Role.EVENT_COORDINATOR)


class IdentityFieldAuthorityTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.url = reverse('auth-register')

    def _payload(self, **overrides):
        payload = {
            'username': 'someone',
            'email': 'someone@example.com',
            'full_name': 'Some One',
            'password': 'StrongPass123!',
            'confirm_password': 'StrongPass123!',
            'role': User.Role.STUDENT,
            'department': self.department.id,
        }
        payload.update(overrides)
        return payload

    def assert_rejected(self, payload, field):
        response = self.client.post(self.url, payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn(field, response.data)
        self.assertFalse(
            User.objects.filter(username=payload['username']).exists(),
            'a rejected registration must not leave an account behind',
        )

    # ------------------------------------------------------------- students

    def test_a_student_cannot_register_without_a_registration_number(self):
        self.assert_rejected(
            self._payload(role=User.Role.STUDENT),
            'university_registration_number',
        )

    def test_a_student_carrying_only_a_faculty_id_is_refused(self):
        # The exact bypass the requirement names: send the student role, but
        # supply the wrong identifier and hope the backend takes either.
        self.assert_rejected(
            self._payload(role=User.Role.STUDENT, faculty_id='FAC-1'),
            'university_registration_number',
        )

    def test_a_student_supplying_both_identifiers_is_refused(self):
        self.assert_rejected(
            self._payload(
                role=User.Role.STUDENT,
                university_registration_number='1AY22MC010',
                faculty_id='FAC-2',
            ),
            'faculty_id',
        )

    # ------------------------------------------------- faculty roles (both)

    def test_neither_faculty_role_can_register_without_a_faculty_id(self):
        for role in FACULTY_ROLES:
            with self.subTest(role=role):
                self.assert_rejected(self._payload(role=role), 'faculty_id')

    def test_neither_faculty_role_can_register_with_only_a_registration_number(self):
        # Refused for the missing Faculty ID rather than for the stray student
        # identifier: that check runs first, and it is the more useful of the
        # two messages because it says what to supply rather than what to drop.
        for role in FACULTY_ROLES:
            with self.subTest(role=role):
                self.assert_rejected(
                    self._payload(role=role, university_registration_number='1AY22MC011'),
                    'faculty_id',
                )

    def test_neither_faculty_role_may_carry_both_identifiers(self):
        for role in FACULTY_ROLES:
            with self.subTest(role=role):
                self.assert_rejected(
                    self._payload(
                        role=role,
                        university_registration_number='1AY22MC012',
                        faculty_id='FAC-3',
                    ),
                    'university_registration_number',
                )

    def test_both_faculty_roles_store_the_faculty_id_and_no_student_identifier(self):
        for index, role in enumerate(FACULTY_ROLES):
            with self.subTest(role=role):
                username = f'facultyperson{index}'
                response = self.client.post(self.url, self._payload(
                    username=username,
                    email=f'{username}@example.com',
                    role=role,
                    faculty_id=f'FAC-STORE-{index}',
                ))
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

                user = User.objects.get(username=username)
                # Stored lowercase whatever case it was sent in.
                self.assertEqual(user.faculty_id, f'fac-store-{index}')
                self.assertIsNone(user.university_registration_number)

    def test_a_faculty_id_is_stored_lowercase_whatever_case_it_arrives_in(self):
        # Pinned deliberately. The identifier is shown back to people — in the
        # Admin console, on a profile, in a report — so two spellings of one id
        # would read as two identifiers. Case-folding on write is what stops
        # that; this asserts the direction, not merely that folding happens.
        for index, sent in enumerate(('FACRUUWH5M', 'FacRuuWh5m', 'facruuwh5m')):
            with self.subTest(sent=sent):
                username = f'caseperson{index}'
                response = self.client.post(self.url, self._payload(
                    username=username,
                    email=f'{username}@example.com',
                    role=User.Role.FACULTY,
                    faculty_id=f'{sent}{index}',
                ))
                self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
                self.assertEqual(
                    User.objects.get(username=username).faculty_id,
                    f'{sent}{index}'.lower(),
                )

    def test_the_same_faculty_id_in_a_different_case_is_still_a_duplicate(self):
        make_faculty('existing', self.department, faculty_id='facruuwh5m')

        self.assert_rejected(
            self._payload(
                username='shouty', email='shouty@example.com',
                role=User.Role.EVENT_COORDINATOR, faculty_id='FACRUUWH5M',
            ),
            'faculty_id',
        )

    # ----------------------------------------------- uniqueness across roles

    def test_a_faculty_id_is_unique_across_both_faculty_roles(self):
        make_faculty('existing', self.department, faculty_id='FAC-SHARED')

        # Registering as the *other* faculty role must not be a way around it.
        self.assert_rejected(
            self._payload(
                username='coordinator', email='coordinator@example.com',
                role=User.Role.EVENT_COORDINATOR, faculty_id='FAC-SHARED',
            ),
            'faculty_id',
        )

    def test_a_registration_number_is_unique_across_students(self):
        make_student('existing', self.department, university_registration_number='1AY22MC099')

        self.assert_rejected(
            self._payload(
                username='another', email='another@example.com',
                role=User.Role.STUDENT, university_registration_number='1AY22MC099',
            ),
            'university_registration_number',
        )

    # ------------------------------------------------ the database holds too

    def test_the_database_refuses_a_student_carrying_a_faculty_id(self):
        # Serializers are one layer. A management command, a data import or a
        # future endpoint bypasses them entirely, so the check constraint has
        # to hold on its own.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create(
                    username='baddata', email='baddata@example.com',
                    role=User.Role.STUDENT, department=self.department,
                    faculty_id='FAC-DB-1',
                )

    def test_the_database_refuses_a_faculty_member_carrying_a_registration_number(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create(
                    username='baddata2', email='baddata2@example.com',
                    role=User.Role.FACULTY, department=self.department,
                    university_registration_number='1AY22MC100',
                )

    def test_the_database_allows_an_event_coordinator_to_hold_a_faculty_id(self):
        # The corrected constraint. Before this, the check named only FACULTY,
        # so an Event Coordinator could not hold the identifier their role is
        # issued and every legitimate promotion collided with it.
        user = User.objects.create(
            username='coordinatordb', email='coordinatordb@example.com',
            role=User.Role.EVENT_COORDINATOR, department=self.department,
            faculty_id='FAC-DB-OK', is_active=True,
        )
        user.refresh_from_db()
        self.assertEqual(user.faculty_id, 'FAC-DB-OK')
