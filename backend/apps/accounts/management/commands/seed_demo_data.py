"""
Development / demonstration seed data.

This command exists so that a new developer, an evaluator or a demo session
can get a database that actually exercises the whole lifecycle — event ->
registration -> participation -> live capture -> evidence -> verification ->
attendance/OD -> achievement -> notification -> analytics — without clicking
through every screen by hand first.

Two rules govern it:

1. It refuses to run unless DEBUG is on. Seed accounts have published,
   well-known passwords; letting this touch a production database would be
   handing out credentials. There is no override flag, deliberately.
2. Every account it creates is named in `DEMO_USERNAMES` and every record it
   creates hangs off one of them, so `--reset` removes exactly what it made
   and nothing else.

The captures it writes are generated placeholder images, not real
photographs — enough for the verification screens to render and for the
evidence-download authorization to be exercised, and obviously synthetic to
anyone looking at them.
"""

import hashlib
import io
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.accounts.models import User, username_validator
from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.audit.models import AuditLog
from apps.colleges.models import College
from apps.departments.models import Department
from apps.events.models import Event
from apps.notifications.models import Notification
from apps.od.models import ODRequest
from apps.participation.models import Participation
from apps.registrations.models import Registration
from apps.verification.models import (
    Evidence,
    EvidenceCapture,
    EvidenceVerification,
    EvidenceVersion,
)

# Development-only. Printed by the command on purpose so nobody has to read
# the source to log in; never reuse it for anything real.
DEMO_PASSWORD = 'DemoPass123!'

# `apps.accounts.models.username_validator` allows lowercase letters and digits
# only, so demo usernames carry no underscore: an account this command creates
# must be one a real user could also have created through the application.
PREFIX = 'demo'

# Reset deletes by this exact list rather than by a `startswith` prefix, so a
# real account that merely happens to begin with "demo" is never caught.
DEMO_USERNAMES = [
    PREFIX + name for name in (
        'admin', 'hodcse', 'hodece', 'facultycse', 'facultyece',
        'student1', 'student2', 'student3', 'student4', 'student5',
    )
]


def _placeholder_image(label):
    """A small labelled JPEG standing in for a live camera capture."""
    image = Image.new('RGB', (480, 360), (52, 84, 122))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 460, 340), outline=(235, 238, 242), width=3)
    draw.text((40, 160), 'DEMO CAPTURE\n' + label, fill=(235, 238, 242))
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=80)
    data = buffer.getvalue()
    return ContentFile(data, name='capture.jpg'), data


class Command(BaseCommand):
    help = (
        'Populate the database with a representative demo dataset (development only). '
        'Refuses to run when DJANGO_DEBUG=False.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete every previously seeded demo record before re-creating them.',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                'seed_demo_data refuses to run with DJANGO_DEBUG=False. Demo accounts use a published '
                'password and must never exist in a production database.'
            )

        if options['reset']:
            self._reset()

        if User.objects.filter(username__in=DEMO_USERNAMES).exists():
            raise CommandError('Demo data is already present. Re-run with --reset to rebuild it from scratch.')

        with transaction.atomic():
            summary = self._seed()

        self.stdout.write(self.style.SUCCESS('Demo data created.'))
        for line in summary:
            self.stdout.write('  ' + line)
        self.stdout.write('')
        self.stdout.write(self.style.WARNING(
            'All demo accounts share the DEVELOPMENT-ONLY password: ' + DEMO_PASSWORD
        ))

    # ------------------------------------------------------------------ teardown

    def _reset(self):
        """Delete in reverse dependency order. Every model below is reached
        from a demo user, so nothing outside the demo dataset is touched."""
        demo_users = User.objects.filter(username__in=DEMO_USERNAMES)
        participations = Participation.objects.filter(student__in=demo_users)
        versions = EvidenceVersion.objects.filter(evidence__participation__in=participations)

        Notification.objects.filter(recipient__in=demo_users).delete()
        AuditLog.objects.filter(actor__in=demo_users).delete()
        Achievement.objects.filter(participation__in=participations).delete()
        Attendance.objects.filter(participation__in=participations).delete()
        ODRequest.objects.filter(participation__in=participations).delete()
        EvidenceVerification.objects.filter(evidence_version__in=versions).delete()
        # Clear the pointer first: Evidence.current_version is SET_NULL while
        # EvidenceVersion -> Evidence is CASCADE, so detaching keeps the
        # delete order unambiguous.
        Evidence.objects.filter(participation__in=participations).update(current_version=None)
        EvidenceCapture.objects.filter(evidence_version__in=versions).delete()
        versions.delete()
        Evidence.objects.filter(participation__in=participations).delete()
        participations.delete()
        Registration.objects.filter(student__in=demo_users).delete()
        Event.objects.filter(created_by__in=demo_users).delete()
        demo_users.delete()
        Department.objects.filter(code__startswith='DEMO').delete()
        College.objects.filter(code__startswith='DEMO').delete()
        self.stdout.write('Previous demo data removed.')

    # ------------------------------------------------------------------ creation

    def _user(self, username, role, department=None, first_name='', last_name='',
              university_registration_number=None, faculty_id=None):
        # Run the application's own validator: a demo account must be one a
        # real user could have created through the API.
        username_validator(PREFIX + username)
        user = User(
            username=PREFIX + username,
            email=PREFIX + username + '@demo.invalid',
            role=role,
            department=department,
            first_name=first_name,
            last_name=last_name,
            # Derived, not a second source of truth: the institution records a
            # name as one string, and these two halves are what the command
            # already had to hand.
            full_name=' '.join(part for part in (first_name, last_name) if part),
            # NULL rather than '': both columns are unique, and Postgres treats
            # each NULL as distinct while a second '' would collide.
            university_registration_number=university_registration_number or None,
            faculty_id=faculty_id or None,
            is_active=True,
        )
        user.set_password(DEMO_PASSWORD)
        user.save()
        return user

    def _seed(self):
        today = timezone.localdate()

        college = College.objects.create(code='DEMOENG', name='Demo Engineering College')
        cse = Department.objects.create(code='DEMOCSE', name='Demo Computer Science')
        ece = Department.objects.create(code='DEMOECE', name='Demo Electronics')

        # An Admin carries neither identifier; both faculty roles carry the
        # college's Faculty ID; students carry a university registration
        # number shaped like a real USN so the screens that display it are
        # exercised at a realistic width.
        admin = self._user('admin', User.Role.ADMIN, first_name='Ada', last_name='Admin')
        cse_event_coordinator = self._user(
            'hodcse', User.Role.EVENT_COORDINATOR, cse, 'Hari', 'Head', faculty_id='demofac001',
        )
        ece_event_coordinator = self._user(
            'hodece', User.Role.EVENT_COORDINATOR, ece, 'Hema', 'Head', faculty_id='demofac002',
        )
        cse_faculty = self._user(
            'facultycse', User.Role.FACULTY, cse, 'Farid', 'Faculty', faculty_id='demofac003',
        )
        ece_faculty = self._user(
            'facultyece', User.Role.FACULTY, ece, 'Fiona', 'Faculty', faculty_id='demofac004',
        )

        students = [
            self._user(
                'student%d' % n, User.Role.STUDENT, cse if n <= 3 else ece,
                'Student%d' % n, 'Demo',
                university_registration_number='1DM22%s%03d' % ('CS' if n <= 3 else 'EC', n),
            )
            for n in range(1, 6)
        ]

        # Events covering every state a user can meet: one happening today
        # (live capture is possible right now), one still open for
        # registration, one already finished, one unpublished draft, and one
        # Admin-created event with no department — the case analytics has to
        # handle without attributing it to any single department.
        today_event = self._event('Demo Hackathon (today)', cse_event_coordinator, college, cse,
                                  event_in=0, reg_from=-7, reg_to=-1,
                                  status=Event.Status.PUBLISHED, category='Technical')
        upcoming_event = self._event('Demo Cultural Fest (upcoming)', cse_event_coordinator, college, cse,
                                     event_in=14, reg_from=-2, reg_to=10,
                                     status=Event.Status.PUBLISHED, category='Cultural')
        past_event = self._event('Demo Sports Meet (completed)', ece_event_coordinator, college, ece,
                                 event_in=-21, reg_from=-30, reg_to=-25,
                                 status=Event.Status.PUBLISHED, category='Sports')
        draft_event = self._event('Demo Workshop (draft)', cse_event_coordinator, college, cse,
                                  event_in=30, reg_from=1, reg_to=20,
                                  status=Event.Status.DRAFT, category='Technical')
        college_wide_event = self._event('Demo Institution Day (college-wide)', admin, college, None,
                                         event_in=21, reg_from=-1, reg_to=15,
                                         status=Event.Status.PUBLISHED, category='Institutional')

        for student in students[:3]:
            Registration.objects.create(student=student, event=today_event)
            Registration.objects.create(student=student, event=upcoming_event)
        for student in students[3:]:
            Registration.objects.create(student=student, event=past_event)
        Registration.objects.create(student=students[0], event=college_wide_event)

        # One cancelled registration so that branch has data too.
        cancelled = Registration.objects.create(student=students[1], event=college_wide_event)
        cancelled.status = Registration.Status.CANCELLED
        cancelled.cancelled_at = timezone.now()
        cancelled.save(update_fields=['status', 'cancelled_at'])

        # Participation + evidence in each state a reviewer sees.
        verified = self._participation_with_evidence(
            students[0], today_event, EvidenceVerification.Decision.VERIFIED, cse_faculty,
            reason='Student and venue clearly visible.')
        self._participation_with_evidence(
            students[1], today_event, EvidenceVerification.Decision.REJECTED, cse_faculty,
            reason='The capture does not show the event venue.')
        self._participation_with_evidence(
            students[2], today_event, None, None)
        overridden = self._participation_with_evidence(
            students[3], past_event, EvidenceVerification.Decision.REJECTED, ece_faculty,
            reason='Background unclear.',
            override_by=ece_event_coordinator, override_decision=EvidenceVerification.Decision.VERIFIED,
            override_reason='Venue confirmed against the organiser list.')

        # Downstream workflows hang off verified participations only.
        Attendance.objects.create(
            participation=verified, registration=verified.registration, requested_by=cse_faculty,
        )
        approved_attendance = Attendance.objects.create(
            participation=overridden, registration=overridden.registration, requested_by=ece_faculty,
        )
        approved_attendance.status = Attendance.Status.APPROVED
        approved_attendance.reviewed_by = ece_event_coordinator
        approved_attendance.reviewed_at = timezone.now()
        approved_attendance.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])

        ODRequest.objects.create(
            participation=verified, requested_by=cse_faculty,
            reason='Represented the department at the inter-college hackathon.')

        Achievement.objects.create(
            participation=verified, created_by=cse_faculty, title='Demo Hackathon - First Place',
            achievement_type='Competition', achievement_date=today_event.event_date,
            status=Achievement.Status.PENDING_APPROVAL)
        Achievement.objects.create(
            participation=overridden, created_by=ece_event_coordinator, title='Demo Sports Meet - Gold Medal',
            achievement_type='Sports', achievement_date=past_event.event_date,
            status=Achievement.Status.APPROVED, reviewed_by=ece_event_coordinator, reviewed_at=timezone.now())

        # Notifications are normally emitted by the services layer as a side
        # effect of the transitions above; a few are written directly here so
        # the notification bell has unread items on first login.
        Notification.objects.create(
            recipient=students[0], notification_type=Notification.Type.EVIDENCE_VERIFIED,
            title='Your participation evidence was verified',
            message='Faculty verified your evidence for Demo Hackathon.',
            action_route='/student/participation')
        Notification.objects.create(
            recipient=students[1], notification_type=Notification.Type.EVIDENCE_REJECTED,
            title='Your participation evidence was rejected',
            message='Faculty rejected your evidence for Demo Hackathon.',
            action_route='/student/participation', priority=Notification.Priority.HIGH)
        Notification.objects.create(
            recipient=cse_faculty, notification_type=Notification.Type.PARTICIPATION_SUBMITTED,
            title='Evidence awaiting your review',
            message='A student submitted participation evidence for Demo Hackathon.',
            action_route='/faculty/verification')

        student_names = ', '.join(s.username for s in students)
        event_titles = ', '.join(repr(e.title) for e in
                                 (today_event, upcoming_event, past_event, draft_event, college_wide_event))
        return [
            'College: %s   Departments: %s, %s' % (college.code, cse.code, ece.code),
            'Admin:    %s' % admin.username,
            'Event Coordinators:     %s (%s), %s (%s)' % (
                cse_event_coordinator.username, cse.code, ece_event_coordinator.username, ece.code,
            ),
            'Faculty:  %s (%s), %s (%s)' % (cse_faculty.username, cse.code, ece_faculty.username, ece.code),
            'Students: %s' % student_names,
            'Events:   %s' % event_titles,
            "Today's event date: %s (the only date its live capture is allowed)" % today,
            'Evidence states: verified, rejected, awaiting review, Event Coordinator-overridden',
        ]

    def _event(self, title, created_by, college, department, event_in, reg_from, reg_to, status, category):
        today = timezone.localdate()
        return Event.objects.create(
            title=title,
            description='Seeded demonstration event. Not a real event.',
            event_date=today + timedelta(days=event_in),
            venue='Demo Main Auditorium',
            category=category,
            conducting_college=college,
            department=department,
            venue_latitude='12.971600',
            venue_longitude='77.594600',
            created_by=created_by,
            status=status,
            registration_start_date=today + timedelta(days=reg_from),
            registration_end_date=today + timedelta(days=reg_to),
        )

    def _participation_with_evidence(self, student, event, decision, reviewer, reason='',
                                     override_by=None, override_decision=None, override_reason=''):
        """Builds a participation with a submitted primary capture and,
        optionally, a Faculty decision and an Event Coordinator override on top of it.

        Written directly against the models rather than through the API
        because the API (correctly) refuses a capture whose event date is not
        today, and the demo needs evidence on a past event too. The rows it
        writes are the same rows the API would have produced.
        """
        registration = Registration.objects.get(student=student, event=event)
        participation = Participation.objects.create(registration=registration)

        evidence = Evidence.objects.create(participation=participation)
        version = EvidenceVersion.objects.create(
            evidence=evidence, version_number=1, submitted_by=student, submitted_at=timezone.now(),
        )
        image, data = _placeholder_image(student.username + ' @ ' + event.title)
        EvidenceCapture.objects.create(
            evidence_version=version,
            capture_role=EvidenceCapture.Role.PRIMARY,
            object_reference=image,
            mime_type='image/jpeg',
            file_size=len(data),
            sha256_hash=hashlib.sha256(data).hexdigest(),
            # Anchored to noon on the event's own date, which is what the
            # capture-date rule requires and what avoids any midnight
            # timezone edge.
            device_capture_timestamp=timezone.make_aware(datetime.combine(event.event_date, time(12, 0))),
            latitude='12.971700',
            longitude='77.594700',
            gps_accuracy=12.0,
            venue_distance=15.0,
            location_warning=False,
        )
        evidence.current_version = version
        evidence.save(update_fields=['current_version'])

        participation.status = Participation.Status.SUBMITTED
        participation.submitted_at = timezone.now()
        participation.save(update_fields=['status', 'submitted_at'])

        if decision is None:
            evidence.status = Evidence.Status.SUBMITTED
            evidence.save(update_fields=['status'])
            return participation

        EvidenceVerification.objects.create(
            evidence_version=version, reviewer=reviewer, decision=decision,
            reason=reason, is_event_coordinator_override=False,
        )
        effective = decision
        if override_by is not None:
            EvidenceVerification.objects.create(
                evidence_version=version, reviewer=override_by, decision=override_decision,
                reason=override_reason, is_event_coordinator_override=True,
            )
            effective = override_decision

        evidence.status = effective
        evidence.save(update_fields=['status'])
        return participation
