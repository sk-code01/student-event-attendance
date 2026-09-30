"""Real cross-connection concurrency for the achievement approval workflow."""

import threading

from django.db import connection
from django.test import TransactionTestCase

from apps.achievements import services
from apps.achievements.models import Achievement

from .helpers import (
    make_college,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_student,
    make_todays_published_event,
    make_verified_participation,
)


class ConcurrentAchievementDecisionTests(TransactionTestCase):
    def _build(self):
        college = make_college()
        department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', department)
        self.faculty = make_faculty('facultycs', department)
        student = make_student('achracestudent', department)
        event = make_todays_published_event(created_by=self.event_coordinator, college=college, department=department)
        participation = make_verified_participation(
            student=student, event=event, reviewer=self.faculty,
        )
        return services.create_achievement(
            participation=participation, creator=self.faculty, submit_for_approval=True,
            title='First Place', description='', achievement_type='Competition',
            achievement_date=event.event_date,
        )

    def test_two_simultaneous_approvals_only_one_wins(self):
        achievement = self._build()
        results = []

        def attempt():
            try:
                services.approve_achievement(achievement=achievement, reviewer=self.event_coordinator)
                results.append('approved')
            except Exception:
                results.append('blocked')
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count('approved'), 1, results)
        self.assertEqual(results.count('blocked'), 1, results)
        self.assertEqual(Achievement.objects.get(pk=achievement.pk).status, Achievement.Status.APPROVED)

    def test_simultaneous_approve_and_reject_leave_exactly_one_outcome(self):
        achievement = self._build()
        results = []

        def approve():
            try:
                services.approve_achievement(achievement=achievement, reviewer=self.event_coordinator)
                results.append('approved')
            except Exception:
                results.append('blocked')
            finally:
                connection.close()

        def reject():
            try:
                services.reject_achievement(achievement=achievement, reviewer=self.event_coordinator, reason='no')
                results.append('rejected')
            except Exception:
                results.append('blocked')
            finally:
                connection.close()

        t1 = threading.Thread(target=approve)
        t2 = threading.Thread(target=reject)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(results.count('blocked'), 1, results)
        refreshed = Achievement.objects.get(pk=achievement.pk)
        self.assertIn(refreshed.status, (Achievement.Status.APPROVED, Achievement.Status.REJECTED))
        self.assertIsNotNone(refreshed.reviewed_at)
