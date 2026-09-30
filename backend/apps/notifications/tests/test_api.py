"""
The notification API: read state, counts, pagination, ordering, and the
IDOR/spoofing surface.

The central security property tested here is that the queryset is scoped to
`recipient=request.user` with no role exemption at all — not even Admin — so
every cross-user access is a plain 404 and no one can mark someone else's mail
as read.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.notifications.models import Notification

from .helpers import AuthMixin, make_admin, make_department, make_faculty, make_event_coordinator, make_student


def make_notification(*, recipient, title='Something happened', is_read=False, **overrides):
    payload = dict(
        recipient=recipient,
        notification_type=Notification.Type.ATTENDANCE_APPROVED,
        title=title,
        message='Details of the thing that happened.',
        action_route='/student/attendance',
        is_read=is_read,
    )
    payload.update(overrides)
    if payload['is_read'] and payload.get('read_at') is None:
        from django.utils import timezone
        payload['read_at'] = timezone.now()
    return Notification.objects.create(**payload)


class NotificationApiTests(AuthMixin, APITestCase):
    def setUp(self):
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.admin = make_admin('sysadmin')
        self.student_a = make_student('studenta', self.cs)
        self.student_b = make_student('studentb', self.cs)

        self.mine = make_notification(recipient=self.student_a, title='Mine')
        self.theirs = make_notification(recipient=self.student_b, title='Theirs')

        self.list_url = reverse('notification-list')
        self.unread_count_url = reverse('notification-unread-count')
        self.read_all_url = reverse('notification-read-all')

    # --- scoping ------------------------------------------------------------

    def test_user_sees_only_their_own_notifications(self):
        self._auth_as('studenta')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['title'] for row in response.data['results']], ['Mine'])

    def test_user_cannot_retrieve_another_users_notification(self):
        self._auth_as('studenta')
        response = self.client.get(reverse('notification-detail', args=[self.theirs.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_cannot_mark_another_users_notification_read(self):
        self._auth_as('studenta')
        response = self.client.post(reverse('notification-read', args=[self.theirs.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Notification.objects.get(pk=self.theirs.id).is_read)

    def test_admin_does_not_see_other_users_notifications_either(self):
        """A notification is personal mail with a personal read state, so even
        Admin is scoped to their own. Admin oversight lives in /audit/."""
        self._auth_as('sysadmin')
        response = self.client.get(self.list_url)
        self.assertEqual(response.data['results'], [])
        self.assertEqual(
            self.client.get(reverse('notification-detail', args=[self.mine.id])).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_unauthenticated_access_is_rejected(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(self.unread_count_url).status_code, status.HTTP_401_UNAUTHORIZED)

    # --- read state ---------------------------------------------------------

    def test_mark_read_sets_is_read_and_server_timestamp(self):
        self._auth_as('studenta')
        response = self.client.post(reverse('notification-read', args=[self.mine.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(response.data['is_read'])
        self.assertIsNotNone(response.data['read_at'])

        refreshed = Notification.objects.get(pk=self.mine.id)
        self.assertTrue(refreshed.is_read)
        self.assertIsNotNone(refreshed.read_at)

    def test_mark_read_is_idempotent(self):
        self._auth_as('studenta')
        first = self.client.post(reverse('notification-read', args=[self.mine.id]))
        original_read_at = first.data['read_at']
        second = self.client.post(reverse('notification-read', args=[self.mine.id]))
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data['read_at'], original_read_at)

    def test_client_cannot_supply_read_at_or_recipient(self):
        self._auth_as('studenta')
        response = self.client.post(
            reverse('notification-read', args=[self.mine.id]),
            {'read_at': '2020-01-01T00:00:00Z', 'recipient': self.student_b.id, 'is_read': False},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refreshed = Notification.objects.get(pk=self.mine.id)
        self.assertEqual(refreshed.recipient_id, self.student_a.id)
        self.assertGreater(refreshed.read_at.year, 2020)

    def test_mark_all_read_only_affects_own_notifications(self):
        make_notification(recipient=self.student_a, title='Second')
        self._auth_as('studenta')
        response = self.client.post(self.read_all_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['marked_read'], 2)

        self.assertEqual(Notification.objects.filter(recipient=self.student_a, is_read=False).count(), 0)
        self.assertFalse(Notification.objects.get(pk=self.theirs.id).is_read)

    def test_unread_count_is_per_user(self):
        make_notification(recipient=self.student_a, title='Second')
        self._auth_as('studenta')
        self.assertEqual(self.client.get(self.unread_count_url).data['unread'], 2)
        self._auth_as('studentb')
        self.assertEqual(self.client.get(self.unread_count_url).data['unread'], 1)

    def test_unread_filter_returns_only_unread(self):
        read_one = make_notification(recipient=self.student_a, title='Already read', is_read=True)
        self._auth_as('studenta')
        response = self.client.get(self.list_url, {'unread': 'true'})
        ids = [row['id'] for row in response.data['results']]
        self.assertIn(self.mine.id, ids)
        self.assertNotIn(read_one.id, ids)

    # --- no write surface ---------------------------------------------------

    def test_there_is_no_create_update_or_delete_endpoint(self):
        self._auth_as('studenta')
        detail = reverse('notification-detail', args=[self.mine.id])
        self.assertEqual(
            self.client.post(self.list_url, {'recipient': self.student_b.id, 'title': 'forged',
                                             'message': 'x', 'notification_type': 'OD_APPROVED'}).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(self.client.patch(detail, {'title': 'edited'}).status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(self.client.delete(detail).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(Notification.objects.get(pk=self.mine.id).title, 'Mine')

    # --- ordering and pagination -------------------------------------------

    def test_notifications_are_newest_first(self):
        second = make_notification(recipient=self.student_a, title='Newer')
        self._auth_as('studenta')
        titles = [row['title'] for row in self.client.get(self.list_url).data['results']]
        self.assertEqual(titles[0], 'Newer')
        self.assertEqual(titles[-1], 'Mine')
        self.assertGreater(second.id, self.mine.id)

    def test_list_is_paginated(self):
        for index in range(25):
            make_notification(recipient=self.student_a, title=f'Bulk {index}')
        self._auth_as('studenta')
        response = self.client.get(self.list_url)
        self.assertEqual(response.data['count'], 26)
        self.assertEqual(len(response.data['results']), 20)  # PAGE_SIZE
        self.assertIsNotNone(response.data['next'])

    def test_marking_read_does_not_change_created_at(self):
        original = Notification.objects.get(pk=self.mine.id).created_at
        self._auth_as('studenta')
        self.client.post(reverse('notification-read', args=[self.mine.id]))
        self.assertEqual(Notification.objects.get(pk=self.mine.id).created_at, original)
