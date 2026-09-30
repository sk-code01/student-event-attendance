from django.conf import settings
from django.db import models
from django.db.models import Q


class Notification(models.Model):
    """
    An in-app message telling one user that something happened which concerns
    them. Delivery is database-backed and in-app only — no email, SMS or push
    channel exists or is stubbed here.

    **Notification is not AuditLog and not Activity.** AuditLog
    (`apps.audit.AuditLog`) is the authoritative security/business trail and is
    written for every meaningful state change regardless of who should hear
    about it. Activity is that same audit trail, re-read and filtered for a
    particular user. A Notification is the third thing: a deliberate,
    addressed message with a read state. One business action may produce all
    three, and they stay separate tables on purpose — deleting or reading a
    notification must never disturb the audit trail.

    Every field except `is_read`/`read_at` is server-generated. `recipient` in
    particular is chosen by the notification service from the business object,
    never accepted from a client.
    """

    class Type(models.TextChoices):
        # Registration approval workflow (Phase 1)
        REGISTRATION_SUBMITTED = 'REGISTRATION_SUBMITTED', 'Registration Submitted'
        REGISTRATION_APPROVED = 'REGISTRATION_APPROVED', 'Registration Approved'
        REGISTRATION_REJECTED = 'REGISTRATION_REJECTED', 'Registration Rejected'
        # Events (Phase 2)
        EVENT_PUBLISHED = 'EVENT_PUBLISHED', 'Event Published'
        EVENT_CANCELLED = 'EVENT_CANCELLED', 'Event Cancelled'
        # Participation / evidence (Phase 3/4)
        PARTICIPATION_SUBMITTED = 'PARTICIPATION_SUBMITTED', 'Participation Submitted'
        EVIDENCE_VERIFIED = 'EVIDENCE_VERIFIED', 'Evidence Verified'
        EVIDENCE_REJECTED = 'EVIDENCE_REJECTED', 'Evidence Rejected'
        EVIDENCE_RESUBMISSION_REQUIRED = 'EVIDENCE_RESUBMISSION_REQUIRED', 'Evidence Resubmission Required'
        EVENT_COORDINATOR_OVERRIDE = 'EVENT_COORDINATOR_OVERRIDE', 'Event Coordinator Override'
        # Attendance / OD / achievements (Phase 5)
        ATTENDANCE_REQUESTED = 'ATTENDANCE_REQUESTED', 'Attendance Requested'
        ATTENDANCE_APPROVED = 'ATTENDANCE_APPROVED', 'Attendance Approved'
        ATTENDANCE_REJECTED = 'ATTENDANCE_REJECTED', 'Attendance Rejected'
        OD_REQUESTED = 'OD_REQUESTED', 'OD Requested'
        OD_APPROVED = 'OD_APPROVED', 'OD Approved'
        OD_REJECTED = 'OD_REJECTED', 'OD Rejected'
        # Certificates
        CERTIFICATE_SUBMITTED = 'CERTIFICATE_SUBMITTED', 'Certificate Submitted'
        CERTIFICATE_VERIFIED = 'CERTIFICATE_VERIFIED', 'Certificate Verified'
        CERTIFICATE_REJECTED = 'CERTIFICATE_REJECTED', 'Certificate Rejected'
        CERTIFICATE_ACCEPTED = 'CERTIFICATE_ACCEPTED', 'Certificate Accepted by Event Coordinator'
        ACHIEVEMENT_CREATED = 'ACHIEVEMENT_CREATED', 'Achievement Created'
        ACHIEVEMENT_APPROVED = 'ACHIEVEMENT_APPROVED', 'Achievement Approved'
        ACHIEVEMENT_REJECTED = 'ACHIEVEMENT_REJECTED', 'Achievement Rejected'

    class Priority(models.TextChoices):
        NORMAL = 'NORMAL', 'Normal'
        HIGH = 'HIGH', 'High'

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications',
        help_text='Server-selected from the business object. Never accepted from client input.',
    )
    notification_type = models.CharField(max_length=40, choices=Type.choices)
    title = models.CharField(max_length=200)
    message = models.TextField()

    related_entity_type = models.CharField(
        max_length=40, blank=True, default='',
        help_text="Lowercase model name, e.g. 'attendance', 'evidence'. Informational only — it grants "
                  'no access; the target endpoint re-authorizes independently.',
    )
    related_entity_id = models.PositiveIntegerField(null=True, blank=True)

    action_route = models.CharField(
        max_length=200, blank=True, default='',
        help_text='An INTERNAL Angular route path such as "/student/attendance". Constrained by '
                  'a DB CheckConstraint to start with "/" and by the service layer to reject "//" '
                  'and any scheme, so a stored value can never become an external redirect.',
    )
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)

    dedupe_key = models.CharField(
        max_length=200, blank=True, default='',
        help_text='Optional idempotency key. When set it is unique, so a retried or double-clicked '
                  'business action reuses the existing row instead of creating a duplicate. Left blank '
                  'for notifications that may legitimately recur.',
    )

    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            # The two queries this table actually serves: "my notifications,
            # newest first" and "how many unread do I have".
            models.Index(fields=['recipient', '-created_at'], name='notif_recipient_created_idx'),
            models.Index(fields=['recipient', 'is_read'], name='notif_recipient_unread_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['dedupe_key'],
                condition=~Q(dedupe_key=''),
                name='unique_notification_dedupe_key',
            ),
            # A read notification always carries its read timestamp, and an
            # unread one never does — so "read by nobody at no time" and
            # "unread but somehow timestamped" are both unrepresentable.
            models.CheckConstraint(
                condition=(
                    Q(is_read=True, read_at__isnull=False) | Q(is_read=False, read_at__isnull=True)
                ),
                name='notification_read_at_matches_is_read',
            ),
            # Defence in depth against redirect injection: whatever the service
            # layer does, the database will not store a route that is not a
            # single-slash-prefixed internal path.
            models.CheckConstraint(
                condition=Q(action_route='') | (Q(action_route__startswith='/') & ~Q(action_route__startswith='//')),
                name='notification_action_route_is_internal',
            ),
        ]

    def __str__(self):
        state = 'read' if self.is_read else 'unread'
        return f'{self.notification_type} to user #{self.recipient_id} ({state})'
