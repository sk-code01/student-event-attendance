"""IDOR and field-spoofing coverage for achievements."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.achievements.models import Achievement

from .helpers import (
    AuthMixin,
    achievement_payload,
    make_admin,
    make_college,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_student,
    make_todays_published_event,
    make_verified_participation,
)


class AchievementIdorTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')

        self.event_coordinator_cs = make_event_coordinator('hodcs', self.cs)
        self.event_coordinator_ec = make_event_coordinator('hodec', self.ec)
        self.faculty_cs = make_faculty('facultycs', self.cs)
        self.faculty_ec = make_faculty('facultyec', self.ec)
        self.admin = make_admin('sysadmin')

        self.student_a = make_student('studenta', self.cs)
        self.student_b = make_student('studentb', self.cs)

        self.event = make_todays_published_event(
            created_by=self.event_coordinator_cs, college=self.college, department=self.cs,
        )
        self.participation_a = make_verified_participation(
            student=self.student_a, event=self.event, reviewer=self.faculty_cs,
        )
        self.participation_b = make_verified_participation(
            student=self.student_b, event=self.event, reviewer=self.faculty_cs,
        )
        self.achievement_a = Achievement.objects.create(
            participation=self.participation_a, created_by=self.faculty_cs,
            title='First Place', achievement_type='Competition',
            achievement_date=self.event.event_date, status=Achievement.Status.PENDING_APPROVAL,
        )
        self.list_url = reverse('achievement-list')
        self.detail_a = reverse('achievement-detail', args=[self.achievement_a.id])

    def test_student_cannot_read_another_students_achievement(self):
        self._auth_as('studentb')
        self.assertEqual(self.client.get(self.detail_a).status_code, status.HTTP_404_NOT_FOUND)

    def test_student_list_only_contains_their_own_records(self):
        self._auth_as('studenta')
        response = self.client.get(self.list_url)
        self.assertEqual([row['id'] for row in response.data['results']], [self.achievement_a.id])
        self._auth_as('studentb')
        self.assertEqual(self.client.get(self.list_url).data['results'], [])

    def test_faculty_cannot_create_an_achievement_for_another_departments_student(self):
        self._auth_as('facultyec')
        response = self.client.post(self.list_url, achievement_payload(self.participation_b))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Achievement.objects.filter(participation=self.participation_b).exists())

    def test_faculty_from_another_department_cannot_read_the_record(self):
        self._auth_as('facultyec')
        self.assertEqual(self.client.get(self.detail_a).status_code, status.HTTP_404_NOT_FOUND)

    def test_event_coordinator_from_another_department_cannot_approve_or_see_the_queue(self):
        self._auth_as('hodec')
        response = self.client.post(reverse('achievement-approve', args=[self.achievement_a.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(self.list_url).data['results'], [])
        self.assertEqual(
            Achievement.objects.get(pk=self.achievement_a.id).status, Achievement.Status.PENDING_APPROVAL,
        )

    def test_student_cannot_edit_an_achievement(self):
        self._auth_as('studenta')
        response = self.client.patch(self.detail_a, {'title': 'Self-promoted'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Achievement.objects.get(pk=self.achievement_a.id).title, 'First Place')

    def test_client_cannot_spoof_status_creator_or_reviewer_on_create(self):
        self._auth_as('facultycs')
        response = self.client.post(self.list_url, achievement_payload(
            self.participation_b,
            status='APPROVED',
            created_by=self.event_coordinator_cs.id,
            reviewed_by=self.event_coordinator_cs.id,
            reviewed_at='2020-01-01T00:00:00Z',
            rejection_reason='injected',
        ))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        created = Achievement.objects.get(pk=response.data['id'])
        self.assertEqual(created.status, Achievement.Status.PENDING_APPROVAL)
        self.assertEqual(created.created_by_id, self.faculty_cs.id)
        self.assertIsNone(created.reviewed_by_id)
        self.assertIsNone(created.reviewed_at)
        self.assertEqual(created.rejection_reason, '')

    def test_patch_cannot_change_status_or_participation(self):
        draft = Achievement.objects.create(
            participation=self.participation_a, created_by=self.faculty_cs,
            title='Draft record', achievement_type='Competition',
            achievement_date=self.event.event_date, status=Achievement.Status.DRAFT,
        )
        self._auth_as('facultycs')
        response = self.client.patch(
            reverse('achievement-detail', args=[draft.id]),
            {'status': 'APPROVED', 'participation': self.participation_b.id, 'title': 'Renamed'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        refreshed = Achievement.objects.get(pk=draft.id)
        self.assertEqual(refreshed.status, Achievement.Status.DRAFT)
        self.assertEqual(refreshed.participation_id, self.participation_a.id)
        self.assertEqual(refreshed.title, 'Renamed')

    def test_reviewer_is_always_the_authenticated_user(self):
        self._auth_as('hodcs')
        response = self.client.post(
            reverse('achievement-approve', args=[self.achievement_a.id]),
            {'reviewed_by': self.faculty_cs.id, 'reviewed_at': '2020-01-01T00:00:00Z'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        refreshed = Achievement.objects.get(pk=self.achievement_a.id)
        self.assertEqual(refreshed.reviewed_by_id, self.event_coordinator_cs.id)
        self.assertGreater(refreshed.reviewed_at.year, 2020)

    def test_admin_can_read_system_wide(self):
        self._auth_as('sysadmin')
        self.assertEqual(self.client.get(self.detail_a).status_code, status.HTTP_200_OK)

    def test_unauthenticated_access_is_rejected(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)
