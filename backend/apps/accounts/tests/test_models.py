from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework.test import APITestCase

from .helpers import make_department, make_event_coordinator, make_user

User = get_user_model()


class UserModelTests(APITestCase):
    def test_create_user_defaults_to_student_role(self):
        user = User.objects.create_user(username='alice', email='alice@example.com', password='StrongPass123!')
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertTrue(user.check_password('StrongPass123!'))

    def test_password_is_hashed_not_plaintext(self):
        user = make_user('hashcheck')
        self.assertNotEqual(user.password, 'StrongPass123!')
        self.assertTrue(user.password.startswith('pbkdf2_') or user.password.startswith('argon2'))

    def test_username_must_be_lowercase_alphanumeric(self):
        user = User(username='Bad-Name!', email='bad@example.com', role=User.Role.STUDENT)
        user.set_password('StrongPass123!')
        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_username_uniqueness_enforced_at_db_level(self):
        make_user('dupuser')
        with self.assertRaises(IntegrityError):
            User.objects.create_user(username='dupuser', email='other@example.com', password='StrongPass123!')

    def test_email_uniqueness_enforced_at_db_level(self):
        make_user('userone', email='shared@example.com')
        with self.assertRaises(IntegrityError):
            User.objects.create_user(username='usertwo', email='shared@example.com', password='StrongPass123!')

    def test_superuser_is_always_forced_to_admin_role(self):
        user = User.objects.create_superuser(username='rootadmin', email='root@example.com', password='StrongPass123!')
        self.assertEqual(user.role, User.Role.ADMIN)


class OneActiveHodPerDepartmentTests(APITestCase):
    def test_second_active_event_coordinator_for_same_department_is_rejected_at_db_level(self):
        dept = make_department('CS', 'Computer Science')
        make_event_coordinator('hod1', dept)
        with self.assertRaises(IntegrityError):
            make_event_coordinator('hod2', dept)

    def test_inactive_event_coordinator_does_not_block_a_new_active_event_coordinator(self):
        dept = make_department('ME', 'Mechanical Engineering')
        old_event_coordinator = make_event_coordinator('oldhod', dept)
        old_event_coordinator.is_active = False
        old_event_coordinator.save(update_fields=['is_active'])
        # Should not raise: the previous Event Coordinator is no longer active.
        make_event_coordinator('newhod', dept)

    def test_two_active_event_coordinators_in_different_departments_is_allowed(self):
        cs = make_department('CS2', 'Computer Science 2')
        ec = make_department('EC2', 'Electronics 2')
        make_event_coordinator('hodcs', cs)
        make_event_coordinator('hodec', ec)
        self.assertEqual(User.objects.filter(role=User.Role.EVENT_COORDINATOR, is_active=True).count(), 2)
