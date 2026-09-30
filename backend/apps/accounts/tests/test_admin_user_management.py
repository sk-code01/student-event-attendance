"""
Admin user management: authorization, filtering, the edit invariants, and
password reset.

These endpoints let one account change another, so the negative cases carry
most of the weight here: who is refused, what change is rejected, and what is
never present in a response.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog

from .helpers import (
    DEFAULT_PASSWORD,
    make_admin,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_student,
    make_user,
)

User = get_user_model()


class AdminUserBaseTests(APITestCase):
    def setUp(self):
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')
        self.admin = make_admin('sysadmin')
        self.event_coordinator_cs = make_event_coordinator('hodcs', self.cs)
        self.faculty_cs = make_faculty('facultycs', self.cs)
        self.student_cs = make_student('studentcs', self.cs)
        self.inactive_student = make_student('pendingcs', self.cs, is_active=False)

    def _auth(self, username, password=DEFAULT_PASSWORD):
        response = self.client.post(
            reverse('token-obtain-pair'), {'username': username, 'password': password},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.data["access"]}')


class AuthorizationTests(AdminUserBaseTests):
    def test_unauthenticated_access_is_refused(self):
        for url in (reverse('admin-user-list'), reverse('admin-user-stats'),
                    reverse('admin-user-detail', args=[self.student_cs.id])):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED, url)

    def test_non_admin_roles_are_refused_every_endpoint(self):
        for username in ('hodcs', 'facultycs', 'studentcs'):
            self._auth(username)
            reads = (reverse('admin-user-list'), reverse('admin-user-stats'),
                     reverse('admin-user-detail', args=[self.student_cs.id]))
            for url in reads:
                self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN,
                                 f'{username} GET {url}')
            writes = (
                ('patch', reverse('admin-user-detail', args=[self.student_cs.id]), {'is_active': False}),
                ('post', reverse('admin-user-activate', args=[self.inactive_student.id]), {}),
                ('post', reverse('admin-user-deactivate', args=[self.student_cs.id]), {}),
                ('post', reverse('admin-user-reset-password', args=[self.student_cs.id]),
                 {'new_password': 'Another$Pass99', 'confirm_password': 'Another$Pass99'}),
            )
            for method, url, body in writes:
                response = getattr(self.client, method)(url, body, format='json')
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, f'{username} {method} {url}')

    def test_an_event_coordinator_cannot_reach_user_management_by_guessing_the_path(self):
        """The Angular guard is UX; this is the boundary that matters."""
        self._auth('hodcs')
        self.assertEqual(
            self.client.get(reverse('admin-user-detail', args=[self.admin.id])).status_code,
            status.HTTP_403_FORBIDDEN,
        )


class ListAndFilterTests(AdminUserBaseTests):
    def setUp(self):
        super().setUp()
        self._auth('sysadmin')

    def test_list_returns_every_account_with_no_sensitive_fields(self):
        response = self.client.get(reverse('admin-user-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], User.objects.count())
        body = response.content.decode()
        for forbidden in ('password', 'pbkdf2_', 'argon2', 'refresh', 'access'):
            self.assertNotIn(forbidden, body.lower(), forbidden)

    def test_search_matches_username_and_email(self):
        for term, expected in (('studentcs', 'studentcs'), ('hodcs@example.com', 'hodcs')):
            response = self.client.get(reverse('admin-user-list'), {'search': term})
            usernames = [row['username'] for row in response.data['results']]
            self.assertIn(expected, usernames, term)

    def test_role_filter(self):
        response = self.client.get(reverse('admin-user-list'), {'role': 'event_coordinator'})
        self.assertEqual([r['username'] for r in response.data['results']], ['hodcs'])

    def test_unknown_role_returns_an_empty_page_not_everything(self):
        response = self.client.get(reverse('admin-user-list'), {'role': 'WIZARD'})
        self.assertEqual(response.data['count'], 0)

    def test_department_filter_including_the_none_case(self):
        in_cs = self.client.get(reverse('admin-user-list'), {'department': self.cs.id})
        self.assertNotIn('sysadmin', [r['username'] for r in in_cs.data['results']])

        no_department = self.client.get(reverse('admin-user-list'), {'department': 'none'})
        self.assertIn('sysadmin', [r['username'] for r in no_department.data['results']])

    def test_non_numeric_department_filter_is_empty_not_a_500(self):
        response = self.client.get(reverse('admin-user-list'), {'department': 'not-a-number'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_status_filter(self):
        active = self.client.get(reverse('admin-user-list'), {'status': 'active'})
        self.assertNotIn('pendingcs', [r['username'] for r in active.data['results']])
        inactive = self.client.get(reverse('admin-user-list'), {'status': 'inactive'})
        self.assertEqual([r['username'] for r in inactive.data['results']], ['pendingcs'])

    def test_pagination_is_applied(self):
        response = self.client.get(reverse('admin-user-list'))
        for key in ('count', 'next', 'previous', 'results'):
            self.assertIn(key, response.data)

    def test_stats_match_the_database(self):
        response = self.client.get(reverse('admin-user-stats'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], User.objects.count())
        self.assertEqual(response.data['active'], User.objects.filter(is_active=True).count())
        self.assertEqual(response.data['inactive'], User.objects.filter(is_active=False).count())
        self.assertEqual(response.data['by_role']['EVENT_COORDINATOR'], 1)

    def test_list_query_count_does_not_grow_with_users(self):
        """select_related('department') is what keeps this flat; without it
        each row would fetch its own department.

        The assertion is that the count does not *grow*, not that it equals
        some literal: the fixed overhead (authenticating the caller, the
        pagination COUNT) is not what this test is about, and pinning it
        would make the test fail for reasons unrelated to an N+1.
        """
        with CaptureQueriesContext(connection) as before:
            self.client.get(reverse('admin-user-list'))
        for n in range(12):
            make_student(f'bulk{n}', self.cs)
        with CaptureQueriesContext(connection) as after:
            self.client.get(reverse('admin-user-list'))
        self.assertEqual(
            len(after), len(before),
            f'query count grew {len(before)} -> {len(after)} as users were added: N+1',
        )


class EditTests(AdminUserBaseTests):
    def setUp(self):
        super().setUp()
        self._auth('sysadmin')

    def test_admin_can_edit_email_and_names(self):
        response = self.client.patch(
            reverse('admin-user-detail', args=[self.student_cs.id]),
            {'email': 'NewAddress@example.com', 'first_name': 'Ada'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.student_cs.refresh_from_db()
        self.assertEqual(self.student_cs.email, 'newaddress@example.com')
        self.assertEqual(self.student_cs.first_name, 'Ada')

    def test_duplicate_email_is_rejected(self):
        response = self.client.patch(
            reverse('admin-user-detail', args=[self.student_cs.id]),
            {'email': self.event_coordinator_cs.email}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)

    def test_put_is_not_allowed(self):
        response = self.client.put(
            reverse('admin-user-detail', args=[self.student_cs.id]), {'email': 'x@example.com'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_username_and_privilege_flags_are_not_writable(self):
        response = self.client.patch(
            reverse('admin-user-detail', args=[self.student_cs.id]),
            {'username': 'hijacked', 'is_staff': True, 'is_superuser': True}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.student_cs.refresh_from_db()
        self.assertEqual(self.student_cs.username, 'studentcs')
        self.assertFalse(self.student_cs.is_staff)
        self.assertFalse(self.student_cs.is_superuser)

    def test_promoting_to_event_coordinator_requires_a_department(self):
        orphan = make_student('orphan', self.cs)
        response = self.client.patch(
            reverse('admin-user-detail', args=[orphan.id]),
            {'role': 'EVENT_COORDINATOR', 'department': None}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('department', response.data)

    def test_a_second_active_event_coordinator_for_one_department_is_refused_cleanly(self):
        """The database has a partial unique index for this; the serializer
        must turn it into a 400 that names the incumbent, not a 500."""
        response = self.client.patch(
            reverse('admin-user-detail', args=[self.faculty_cs.id]),
            {'role': 'EVENT_COORDINATOR', 'department': self.cs.id}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('hodcs', str(response.data['role']))
        self.faculty_cs.refresh_from_db()
        self.assertEqual(self.faculty_cs.role, User.Role.FACULTY)

    def test_promoting_to_event_coordinator_in_a_department_without_one_succeeds(self):
        response = self.client.patch(
            reverse('admin-user-detail', args=[self.faculty_cs.id]),
            {'role': 'EVENT_COORDINATOR', 'department': self.ec.id}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.faculty_cs.refresh_from_db()
        self.assertEqual(self.faculty_cs.role, User.Role.EVENT_COORDINATOR)
        self.assertEqual(self.faculty_cs.department, self.ec)

    def test_moving_an_event_coordinator_to_another_department_keeps_integrity(self):
        response = self.client.patch(
            reverse('admin-user-detail', args=[self.event_coordinator_cs.id]),
            {'department': self.ec.id}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(User.objects.filter(
            role=User.Role.EVENT_COORDINATOR, is_active=True, department=self.ec,
        ).count(), 1)
        self.assertEqual(User.objects.filter(
            role=User.Role.EVENT_COORDINATOR, is_active=True, department=self.cs,
        ).count(), 0)

    def test_the_last_active_admin_cannot_be_demoted(self):
        response = self.client.patch(
            reverse('admin-user-detail', args=[self.admin.id]), {'role': 'FACULTY'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.role, User.Role.ADMIN)

    def test_the_last_active_admin_cannot_be_deactivated(self):
        response = self.client.patch(
            reverse('admin-user-detail', args=[self.admin.id]), {'is_active': False}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_an_admin_can_be_demoted_once_another_admin_exists(self):
        make_admin('secondadmin')
        response = self.client.patch(
            reverse('admin-user-detail', args=[self.admin.id]),
            {'role': 'FACULTY', 'department': self.cs.id}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_an_admin_cannot_deactivate_their_own_account(self):
        make_admin('secondadmin')
        response = self.client.patch(
            reverse('admin-user-detail', args=[self.admin.id]), {'is_active': False}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('is_active', response.data)

    def test_a_superuser_role_cannot_be_changed(self):
        root = make_admin('rootuser')
        root.is_superuser = True
        root.is_staff = True
        root.save()
        response = self.client.patch(
            reverse('admin-user-detail', args=[root.id]),
            {'role': 'STUDENT', 'department': self.cs.id}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_an_edit_is_audited_with_the_fields_that_changed(self):
        self.client.patch(
            reverse('admin-user-detail', args=[self.student_cs.id]),
            {'first_name': 'Grace'}, format='json',
        )
        entry = AuditLog.objects.filter(action='ADMIN_USER_UPDATED').first()
        self.assertIsNotNone(entry)
        self.assertIn('studentcs', entry.description)
        self.assertIn('first_name', entry.description)

    def test_a_database_constraint_collision_becomes_a_400_not_a_500(self):
        """Two Admins promoting different accounts to Event Coordinator of one department can
        each pass the serializer check and only collide at the partial unique
        index. The loser of that race must get a clean 400."""
        from unittest import mock

        target = make_faculty('racefaculty', self.ec)
        with mock.patch.object(
            User, 'full_clean',
            side_effect=IntegrityError('duplicate key value violates unique constraint '
                                       '"unique_active_event_coordinator_per_department"'),
        ):
            response = self.client.patch(
                reverse('admin-user-detail', args=[target.id]),
                {'role': 'EVENT_COORDINATOR', 'department': self.ec.id}, format='json',
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn('already has an active Event Coordinator', str(response.data))
        # The internal index name must not reach the client.
        self.assertNotIn('unique_active_event_coordinator_per_department', str(response.data))

    def test_a_no_op_patch_writes_no_audit_entry(self):
        self.client.patch(
            reverse('admin-user-detail', args=[self.student_cs.id]),
            {'first_name': self.student_cs.first_name}, format='json',
        )
        self.assertFalse(AuditLog.objects.filter(action='ADMIN_USER_UPDATED').exists())


class ActivationTests(AdminUserBaseTests):
    def setUp(self):
        super().setUp()
        self._auth('sysadmin')

    def test_activate_and_deactivate(self):
        response = self.client.post(reverse('admin-user-activate', args=[self.inactive_student.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.inactive_student.refresh_from_db()
        self.assertTrue(self.inactive_student.is_active)

        response = self.client.post(reverse('admin-user-deactivate', args=[self.inactive_student.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.inactive_student.refresh_from_db()
        self.assertFalse(self.inactive_student.is_active)

    def test_repeating_the_same_action_is_a_clean_400(self):
        self.assertEqual(
            self.client.post(reverse('admin-user-activate', args=[self.student_cs.id])).status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            self.client.post(reverse('admin-user-deactivate', args=[self.inactive_student.id])).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_activation_obeys_the_one_active_event_coordinator_rule(self):
        """CS already has an active Event Coordinator. Reactivating a second Event Coordinator for CS
        must be refused by the serializer, not left to the database to reject
        with an IntegrityError surfacing as a 500."""
        spare = make_user('sparehod', role=User.Role.EVENT_COORDINATOR, department=self.cs, is_active=False)
        response = self.client.post(reverse('admin-user-activate', args=[spare.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn('hodcs', str(response.data))
        spare.refresh_from_db()
        self.assertFalse(spare.is_active)

    def test_deactivating_the_last_admin_is_refused(self):
        self.assertEqual(
            self.client.post(reverse('admin-user-deactivate', args=[self.admin.id])).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_a_deactivated_user_can_no_longer_log_in(self):
        self.client.post(reverse('admin-user-deactivate', args=[self.student_cs.id]))
        self.client.credentials()
        response = self.client.post(
            reverse('token-obtain-pair'), {'username': 'studentcs', 'password': DEFAULT_PASSWORD},
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_activation_is_audited(self):
        self.client.post(reverse('admin-user-activate', args=[self.inactive_student.id]))
        self.assertTrue(AuditLog.objects.filter(action='ADMIN_USER_ACTIVATED').exists())
        self.client.post(reverse('admin-user-deactivate', args=[self.inactive_student.id]))
        self.assertTrue(AuditLog.objects.filter(action='ADMIN_USER_DEACTIVATED').exists())


class PasswordResetTests(AdminUserBaseTests):
    URL_BODY = {'new_password': 'Repl@cement2026', 'confirm_password': 'Repl@cement2026'}

    def setUp(self):
        super().setUp()
        self._auth('sysadmin')

    def _url(self):
        return reverse('admin-user-reset-password', args=[self.student_cs.id])

    def test_reset_changes_the_password_and_the_user_can_log_in_with_it(self):
        response = self.client.post(self._url(), self.URL_BODY, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.client.credentials()
        old = self.client.post(
            reverse('token-obtain-pair'), {'username': 'studentcs', 'password': DEFAULT_PASSWORD},
        )
        self.assertEqual(old.status_code, status.HTTP_401_UNAUTHORIZED)
        new = self.client.post(
            reverse('token-obtain-pair'), {'username': 'studentcs', 'password': self.URL_BODY['new_password']},
        )
        self.assertEqual(new.status_code, status.HTTP_200_OK)

    def test_the_response_never_contains_password_material(self):
        response = self.client.post(self._url(), self.URL_BODY, format='json')
        body = response.content.decode()
        self.assertNotIn(self.URL_BODY['new_password'], body)
        self.assertNotIn('password_hash', body)
        self.student_cs.refresh_from_db()
        self.assertNotIn(self.student_cs.password, body)

    def test_the_stored_password_is_hashed_not_plaintext(self):
        self.client.post(self._url(), self.URL_BODY, format='json')
        self.student_cs.refresh_from_db()
        self.assertNotEqual(self.student_cs.password, self.URL_BODY['new_password'])
        self.assertTrue(self.student_cs.check_password(self.URL_BODY['new_password']))

    def test_mismatched_confirmation_is_rejected(self):
        response = self.client.post(
            self._url(), {'new_password': 'Repl@cement2026', 'confirm_password': 'Different1!'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('confirm_password', response.data)

    def test_a_weak_password_is_rejected_by_djangos_validators(self):
        response = self.client.post(
            self._url(), {'new_password': '12345678', 'confirm_password': '12345678'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('new_password', response.data)
        self.student_cs.refresh_from_db()
        self.assertTrue(self.student_cs.check_password(DEFAULT_PASSWORD))

    def test_reset_is_audited_without_the_password(self):
        self.client.post(self._url(), self.URL_BODY, format='json')
        entry = AuditLog.objects.filter(action='ADMIN_PASSWORD_RESET').first()
        self.assertIsNotNone(entry)
        self.assertIn('studentcs', entry.description)
        self.assertNotIn(self.URL_BODY['new_password'], entry.description)

    def test_reset_revokes_the_targets_existing_refresh_tokens(self):
        """A reset exists to take an account back under control, so a session
        opened before it must not survive it."""
        self.client.credentials()
        login = self.client.post(
            reverse('token-obtain-pair'), {'username': 'studentcs', 'password': DEFAULT_PASSWORD},
        )
        stolen_refresh = login.data['refresh']

        self._auth('sysadmin')
        self.client.post(self._url(), self.URL_BODY, format='json')

        self.client.credentials()
        replay = self.client.post(reverse('token-refresh'), {'refresh': stolen_refresh})
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)


class DetailTests(AdminUserBaseTests):
    def setUp(self):
        super().setUp()
        self._auth('sysadmin')

    def test_detail_returns_the_account_without_sensitive_fields(self):
        response = self.client.get(reverse('admin-user-detail', args=[self.student_cs.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'studentcs')
        self.assertNotIn('password', response.data)

    def test_a_missing_user_is_404(self):
        self.assertEqual(
            self.client.get(reverse('admin-user-detail', args=[999999])).status_code,
            status.HTTP_404_NOT_FOUND,
        )
