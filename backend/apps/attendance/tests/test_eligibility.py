"""
The eligibility gate: attendance may only be requested for a participation
whose *effective* evidence decision is VERIFIED.

The two cases that distinguish "effective decision" from "Faculty decision"
are the whole reason this file exists:
  * Faculty REJECTED, Event Coordinator override VERIFIED -> eligible
  * Faculty VERIFIED, Event Coordinator override REJECTED -> NOT eligible
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.attendance.models import Attendance
from apps.verification.models import EvidenceVerification

from .helpers import (
    AuthMixin,
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


class AttendanceEligibilityTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.url = reverse('attendance-list')

    def _request_for(self, participation):
        self._auth_as('facultycs')
        return self.client.post(self.url, {'participation': participation.id})

    def test_verified_participation_is_eligible(self):
        student = make_student('elig1', self.cs)
        participation = make_verified_participation(student=student, event=self.event, reviewer=self.faculty)
        response = self._request_for(participation)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], Attendance.Status.PENDING)
        self.assertEqual(response.data['student']['username'], 'elig1')

    def test_participation_without_any_evidence_is_not_eligible(self):
        student = make_student('elig2', self.cs)
        participation = make_participation(student=student, event=self.event)
        response = self._request_for(participation)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Attendance.objects.exists())

    def test_submitted_but_undecided_evidence_is_not_eligible(self):
        student = make_student('elig3', self.cs)
        participation = make_participation(student=student, event=self.event)
        make_submitted_evidence(participation=participation)
        response = self._request_for(participation)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejected_evidence_is_not_eligible(self):
        student = make_student('elig4', self.cs)
        participation = make_decided_participation(
            student=student, event=self.event, reviewer=self.faculty, decision=Decision.REJECTED,
        )
        response = self._request_for(participation)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_resubmission_required_evidence_is_not_eligible(self):
        student = make_student('elig5', self.cs)
        participation = make_decided_participation(
            student=student, event=self.event, reviewer=self.faculty, decision=Decision.RESUBMISSION_REQUIRED,
        )
        response = self._request_for(participation)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_faculty_rejected_but_event_coordinator_override_verified_is_eligible(self):
        student = make_student('elig6', self.cs)
        participation = make_decided_participation(
            student=student, event=self.event, reviewer=self.faculty, decision=Decision.REJECTED,
            override_by=self.event_coordinator, override_decision=Decision.VERIFIED,
        )
        response = self._request_for(participation)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_faculty_verified_but_event_coordinator_override_rejected_is_not_eligible(self):
        student = make_student('elig7', self.cs)
        participation = make_decided_participation(
            student=student, event=self.event, reviewer=self.faculty, decision=Decision.VERIFIED,
            override_by=self.event_coordinator, override_decision=Decision.REJECTED,
        )
        response = self._request_for(participation)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Attendance.objects.exists())

    def test_duplicate_request_for_same_participation_is_rejected(self):
        student = make_student('elig8', self.cs)
        participation = make_verified_participation(student=student, event=self.event, reviewer=self.faculty)
        first = self._request_for(participation)
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.client.post(self.url, {'participation': participation.id})
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Attendance.objects.filter(participation=participation).count(), 1)
