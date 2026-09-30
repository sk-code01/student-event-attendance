"""
Achievement creation and approval.

Faculty create -> PENDING_APPROVAL (or DRAFT while still editing) -> Event Coordinator
approves/rejects. Event Coordinator/Admin create -> APPROVED immediately, because they
already hold the approving authority and routing them through their own queue
would be an approval loop. Only APPROVED records are official.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.achievements.models import Achievement
from apps.audit.models import AuditLog
from apps.verification.models import EvidenceVerification

from .helpers import (
    AuthMixin,
    achievement_payload,
    make_admin,
    make_college,
    make_decided_participation,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_participation,
    make_student,
    make_submitted_evidence,
    make_todays_published_event,
    make_verified_participation,
)

Decision = EvidenceVerification.Decision


class AchievementCreationTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.admin = make_admin('sysadmin')
        self.student = make_student('achstudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        self.list_url = reverse('achievement-list')

    def test_faculty_creation_goes_to_pending_approval(self):
        self._auth_as('facultycs')
        response = self.client.post(self.list_url, achievement_payload(self.participation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], Achievement.Status.PENDING_APPROVAL)
        self.assertFalse(response.data['is_official'])
        self.assertEqual(response.data['created_by']['username'], 'facultycs')
        self.assertIsNone(response.data['reviewed_by'])
        self.assertTrue(AuditLog.objects.filter(action='ACHIEVEMENT_CREATED', actor=self.faculty).exists())

    def test_faculty_can_keep_a_draft_then_submit_it(self):
        self._auth_as('facultycs')
        created = self.client.post(
            self.list_url, achievement_payload(self.participation, submit_for_approval=False),
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(created.data['status'], Achievement.Status.DRAFT)

        submitted = self.client.post(reverse('achievement-submit', args=[created.data['id']]))
        self.assertEqual(submitted.status_code, status.HTTP_200_OK, submitted.data)
        self.assertEqual(submitted.data['status'], Achievement.Status.PENDING_APPROVAL)

    def test_event_coordinator_creation_is_authoritative_immediately(self):
        self._auth_as('hodcs')
        response = self.client.post(self.list_url, achievement_payload(self.participation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], Achievement.Status.APPROVED)
        self.assertTrue(response.data['is_official'])
        self.assertEqual(response.data['reviewed_by']['username'], 'hodcs')

    def test_admin_creation_is_authoritative_immediately(self):
        self._auth_as('sysadmin')
        response = self.client.post(self.list_url, achievement_payload(self.participation))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], Achievement.Status.APPROVED)

    def test_student_cannot_create_an_achievement_for_themselves(self):
        self._auth_as('achstudent')
        response = self.client.post(self.list_url, achievement_payload(self.participation))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Achievement.objects.exists())

    def test_a_verified_participation_does_not_create_an_achievement_by_itself(self):
        """Verification alone must never produce an achievement row."""
        self.assertFalse(Achievement.objects.filter(participation=self.participation).exists())

    def test_multiple_achievements_from_the_same_participation_are_allowed(self):
        self._auth_as('facultycs')
        first = self.client.post(self.list_url, achievement_payload(self.participation, title='First Place'))
        second = self.client.post(self.list_url, achievement_payload(self.participation, title='Best Design'))
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED, second.data)
        self.assertEqual(Achievement.objects.filter(participation=self.participation).count(), 2)


class AchievementEligibilityTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.list_url = reverse('achievement-list')

    def _create_for(self, participation, **overrides):
        self._auth_as('facultycs')
        return self.client.post(self.list_url, achievement_payload(participation, **overrides))

    def test_unverified_participation_is_refused(self):
        student = make_student('acheli1', self.cs)
        participation = make_participation(student=student, event=self.event)
        make_submitted_evidence(participation=participation)
        self.assertEqual(self._create_for(participation).status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejected_evidence_is_refused(self):
        student = make_student('acheli2', self.cs)
        participation = make_decided_participation(
            student=student, event=self.event, reviewer=self.faculty, decision=Decision.REJECTED,
        )
        self.assertEqual(self._create_for(participation).status_code, status.HTTP_400_BAD_REQUEST)

    def test_event_coordinator_override_verified_makes_it_eligible(self):
        student = make_student('acheli3', self.cs)
        participation = make_decided_participation(
            student=student, event=self.event, reviewer=self.faculty, decision=Decision.REJECTED,
            override_by=self.event_coordinator, override_decision=Decision.VERIFIED,
        )
        self.assertEqual(self._create_for(participation).status_code, status.HTTP_201_CREATED)

    def test_event_coordinator_override_rejected_makes_it_ineligible(self):
        student = make_student('acheli4', self.cs)
        participation = make_decided_participation(
            student=student, event=self.event, reviewer=self.faculty, decision=Decision.VERIFIED,
            override_by=self.event_coordinator, override_decision=Decision.REJECTED,
        )
        self.assertEqual(self._create_for(participation).status_code, status.HTTP_400_BAD_REQUEST)

    def test_achievement_date_before_the_event_is_refused(self):
        student = make_student('acheli5', self.cs)
        participation = make_verified_participation(student=student, event=self.event, reviewer=self.faculty)
        earlier = self.event.event_date - timedelta(days=1)
        response = self._create_for(participation, achievement_date=str(earlier))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('achievement_date', response.data)

    def test_achievement_date_in_the_future_is_refused(self):
        student = make_student('acheli6', self.cs)
        participation = make_verified_participation(student=student, event=self.event, reviewer=self.faculty)
        future = timezone.localdate() + timedelta(days=1)
        response = self._create_for(participation, achievement_date=str(future))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class AchievementApprovalTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.student = make_student('achstudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        self.list_url = reverse('achievement-list')
        self._auth_as('facultycs')
        created = self.client.post(self.list_url, achievement_payload(self.participation))
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.achievement_id = created.data['id']

    def test_event_coordinator_can_approve_and_it_becomes_official(self):
        self._auth_as('hodcs')
        response = self.client.post(reverse('achievement-approve', args=[self.achievement_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], Achievement.Status.APPROVED)
        self.assertTrue(response.data['is_official'])
        self.assertEqual(response.data['reviewed_by']['username'], 'hodcs')
        self.assertTrue(AuditLog.objects.filter(action='ACHIEVEMENT_APPROVED').exists())

    def test_faculty_cannot_approve_their_own_achievement(self):
        response = self.client.post(reverse('achievement-approve', args=[self.achievement_id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            Achievement.objects.get(pk=self.achievement_id).status, Achievement.Status.PENDING_APPROVAL,
        )

    def test_student_cannot_approve_an_achievement(self):
        self._auth_as('achstudent')
        response = self.client.post(reverse('achievement-approve', args=[self.achievement_id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_reject_requires_a_reason(self):
        self._auth_as('hodcs')
        response = self.client.post(reverse('achievement-reject', args=[self.achievement_id]), {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_event_coordinator_can_reject_with_a_reason_and_the_record_is_preserved(self):
        self._auth_as('hodcs')
        response = self.client.post(
            reverse('achievement-reject', args=[self.achievement_id]), {'reason': 'Not an official placement'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], Achievement.Status.REJECTED)
        self.assertEqual(response.data['rejection_reason'], 'Not an official placement')
        self.assertFalse(response.data['is_official'])
        self.assertTrue(Achievement.objects.filter(pk=self.achievement_id).exists())

    def test_a_decided_achievement_cannot_be_decided_again(self):
        self._auth_as('hodcs')
        self.client.post(reverse('achievement-approve', args=[self.achievement_id]))
        response = self.client.post(
            reverse('achievement-reject', args=[self.achievement_id]), {'reason': 'changed my mind'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Achievement.objects.get(pk=self.achievement_id).status, Achievement.Status.APPROVED)

    def test_an_approved_achievement_cannot_be_edited(self):
        self._auth_as('hodcs')
        self.client.post(reverse('achievement-approve', args=[self.achievement_id]))
        self._auth_as('facultycs')
        response = self.client.patch(
            reverse('achievement-detail', args=[self.achievement_id]), {'title': 'Tampered'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Achievement.objects.get(pk=self.achievement_id).title, 'First Place')

    def test_a_pending_achievement_cannot_be_edited_either(self):
        response = self.client.patch(
            reverse('achievement-detail', args=[self.achievement_id]), {'title': 'Moving target'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_sees_status_and_can_distinguish_official_records(self):
        self._auth_as('hodcs')
        self.client.post(reverse('achievement-reject', args=[self.achievement_id]), {'reason': 'not official'})
        self._auth_as('achstudent')
        response = self.client.get(reverse('achievement-detail', args=[self.achievement_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Achievement.Status.REJECTED)
        self.assertFalse(response.data['is_official'])
        self.assertEqual(response.data['rejection_reason'], 'not official')


class AchievementDraftEditingTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.faculty2 = make_faculty('facultycs2', self.cs)
        self.student = make_student('draftstudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        self._auth_as('facultycs')
        created = self.client.post(
            reverse('achievement-list'), achievement_payload(self.participation, submit_for_approval=False),
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.achievement_id = created.data['id']
        self.detail_url = reverse('achievement-detail', args=[self.achievement_id])

    def test_creator_can_edit_their_own_draft(self):
        response = self.client.patch(self.detail_url, {'title': 'Runner Up'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['title'], 'Runner Up')
        self.assertTrue(AuditLog.objects.filter(action='ACHIEVEMENT_UPDATED').exists())

    def test_another_faculty_cannot_edit_someone_elses_draft(self):
        self._auth_as('facultycs2')
        response = self.client.patch(self.detail_url, {'title': 'Hijacked'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Achievement.objects.get(pk=self.achievement_id).title, 'First Place')

    def test_editing_cannot_set_an_invalid_achievement_date(self):
        earlier = self.event.event_date - timedelta(days=3)
        response = self.client.patch(self.detail_url, {'achievement_date': str(earlier)})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_draft_cannot_be_approved_without_being_submitted_first(self):
        self._auth_as('hodcs')
        response = self.client.post(reverse('achievement-approve', args=[self.achievement_id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Achievement.objects.get(pk=self.achievement_id).status, Achievement.Status.DRAFT)
