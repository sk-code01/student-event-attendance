import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.participation.geocoding import Precision
from apps.participation.storage import private_capture_storage

MIME_EXTENSIONS = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
}


def capture_upload_path(instance: 'EvidenceCapture', filename: str) -> str:
    """Server-generated object key — identical convention to Phase 3's
    ParticipationCapture.capture_upload_path, just keyed off the evidence
    version's participation instead. The client-supplied `filename` is
    never used."""
    extension = MIME_EXTENSIONS.get(instance.mime_type, 'bin')
    participation = instance.evidence_version.evidence.participation
    return (
        f'{participation.student_id}/{participation.id}/'
        f'{instance.evidence_version.version_number}/{uuid.uuid4().hex}.{extension}'
    )


class Evidence(models.Model):
    """
    Evidence != Participation: a Participation records that a student ran
    the live-capture workflow at all; Evidence tracks the versioned trail of
    submissions and Faculty/Event Coordinator decisions made against that participation.
    `OneToOneField` is the DB-level enforcement of "one Evidence per
    Participation".

    `status` is deliberately the smallest clean state model
    (SUBMITTED/UNDER_REVIEW/VERIFIED/REJECTED/RESUBMISSION_REQUIRED) and is
    only meaningful once the current version has actually been submitted —
    an Evidence row is created together with its first (still in-progress)
    EvidenceVersion, but `status` is not treated as authoritative by any
    reader until `current_version.submitted_at` is set. Serializers expose
    that in-progress state as a computed flag rather than adding a sixth DB
    enum value, keeping the persisted state machine exactly as specified.
    All transitions happen inside apps.verification.services, never by a
    client directly setting this field.
    """

    class Status(models.TextChoices):
        SUBMITTED = 'SUBMITTED', 'Submitted'
        UNDER_REVIEW = 'UNDER_REVIEW', 'Under Review'
        VERIFIED = 'VERIFIED', 'Verified'
        REJECTED = 'REJECTED', 'Rejected'
        RESUBMISSION_REQUIRED = 'RESUBMISSION_REQUIRED', 'Resubmission Required'

    participation = models.OneToOneField(
        'participation.Participation', on_delete=models.PROTECT, related_name='evidence',
    )
    current_version = models.ForeignKey(
        'EvidenceVersion', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.SUBMITTED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status'])]

    def __str__(self):
        return f'Evidence #{self.pk} for participation #{self.participation_id} ({self.status})'


class EvidenceVersion(models.Model):
    """
    Every resubmission creates a NEW row here — a previous version is never
    overwritten or deleted, so Version 1 stays readable forever even after
    Version 2 exists. `version_number` is always server-generated (never
    accepted from the client) and DB-uniqueness-enforced per evidence via
    the constraint below, which also protects against two concurrent
    resubmission requests both computing the same "next" number — see
    apps.verification.services.open_evidence_version, which additionally
    takes a row lock on the parent Evidence for the same reason.

    `submitted_at` is null while the student is still capturing/uploading
    for this version; it is set exactly once, by
    apps.verification.services.submit_version.
    """

    evidence = models.ForeignKey(Evidence, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    submission_reason = models.TextField(
        blank=True, default='',
        help_text='Set for version 2+: a copy of the Faculty resubmission-request reason that triggered it.',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['version_number']
        constraints = [
            models.UniqueConstraint(fields=['evidence', 'version_number'], name='unique_version_number_per_evidence'),
        ]

    def __str__(self):
        return f'Evidence #{self.evidence_id} v{self.version_number}'

    @property
    def has_primary_capture(self) -> bool:
        if 'captures' in getattr(self, '_prefetched_objects_cache', {}):
            return any(c.capture_role == EvidenceCapture.Role.PRIMARY for c in self.captures.all())
        return self.captures.filter(capture_role=EvidenceCapture.Role.PRIMARY).exists()

    @property
    def effective_verification(self):
        """Event Coordinator override precedence: IF a valid Event Coordinator override exists on this
        version -> that is effective; ELSE -> the latest Faculty decision.
        The override never overwrites or deletes the Faculty row — both are
        preserved and this is purely a read-time precedence computation."""
        if 'verifications' in getattr(self, '_prefetched_objects_cache', {}):
            rows = sorted(self.verifications.all(), key=lambda v: v.created_at, reverse=True)
            override = next((v for v in rows if v.is_event_coordinator_override), None)
            return override or next((v for v in rows if not v.is_event_coordinator_override), None)
        override = self.verifications.filter(is_event_coordinator_override=True).order_by('-created_at').first()
        if override is not None:
            return override
        return self.verifications.filter(is_event_coordinator_override=False).order_by('-created_at').first()


class EvidenceCapture(models.Model):
    """
    Phase 4's finalized evidence-capture record — the direct successor of
    Phase 3's `ParticipationCapture`, migrated onto `evidence_version`
    instead of `participation` (see the apps.verification data migration).
    Field set matches the finalized Phase 4 spec; `validation_status` is
    always VALID in this phase because validation happens synchronously at
    upload time (an invalid capture raises before a row is ever created) —
    the field exists for schema fidelity and to support a future async
    validation pipeline without another migration.
    """

    class Role(models.TextChoices):
        PRIMARY = 'PRIMARY', 'Primary'
        ADDITIONAL = 'ADDITIONAL', 'Additional'

    class ValidationStatus(models.TextChoices):
        VALID = 'VALID', 'Valid'

    evidence_version = models.ForeignKey(EvidenceVersion, on_delete=models.CASCADE, related_name='captures')
    capture_role = models.CharField(max_length=20, choices=Role.choices)
    object_reference = models.FileField(upload_to=capture_upload_path, storage=private_capture_storage)
    mime_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField()
    sha256_hash = models.CharField(max_length=64, db_index=True)

    device_capture_timestamp = models.DateTimeField(
        help_text='Client-reported capture time. Evidence metadata, not a trusted security value.',
    )
    server_received_timestamp = models.DateTimeField(auto_now_add=True)

    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    gps_accuracy = models.FloatField(help_text='Meters, as reported by the browser Geolocation API.')
    venue_distance = models.FloatField(
        null=True, blank=True, help_text='Meters from the event venue, when venue coordinates are configured.',
    )
    location_warning = models.BooleanField(
        default=False,
        help_text='True when venue_distance exceeds VENUE_WARNING_DISTANCE_METERS. Never blocks submission.',
    )
    validation_status = models.CharField(
        max_length=20, choices=ValidationStatus.choices, default=ValidationStatus.VALID,
    )

    # Human-readable location, resolved from the coordinates above at capture
    # time. The coordinates remain the evidence and are never replaced by this:
    # an address is an aid to reading them, and is blank whenever the lookup is
    # switched off, unavailable, or not confident enough to be worth stating.
    resolved_address = models.TextField(
        blank=True, default='',
        help_text='Reverse-geocoded address. Blank when it could not be resolved.',
    )
    address_precision = models.CharField(
        max_length=20, choices=Precision.CHOICES, default=Precision.UNRESOLVED,
        help_text=(
            'EXACT only when the provider placed this at a specific building AND the '
            'GPS accuracy was good enough for that to mean anything.'
        ),
    )
    address_provider = models.CharField(max_length=40, blank=True, default='')
    address_resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['evidence_version'],
                condition=Q(capture_role='PRIMARY'),
                name='unique_primary_capture_per_evidence_version',
            ),
        ]

    def __str__(self):
        return f'{self.capture_role} capture for evidence version #{self.evidence_version_id}'

    @property
    def location_summary(self) -> str:
        """What a reviewer should be shown for this capture's location.

        States the address only when there is one, and is explicit about its
        precision rather than letting an approximate result read as an exact
        one. With no address it falls back to the coordinates and their
        accuracy, which is the honest description of what is actually known.
        """
        accuracy = f'{self.gps_accuracy:.0f} m' if self.gps_accuracy is not None else 'unknown'
        if self.resolved_address and self.address_precision == Precision.EXACT:
            return f'{self.resolved_address} (GPS accurate to {accuracy})'
        if self.resolved_address:
            return f'Near {self.resolved_address} (GPS accurate to {accuracy})'
        return f'{self.latitude}, {self.longitude} (GPS accurate to {accuracy}; address not resolved)'


class EvidenceVerification(models.Model):
    """
    One row per Faculty decision or Event Coordinator override — history is append-only,
    never overwritten or deleted, so every prior decision stays fully
    readable. A normal workflow has one current Faculty decision per
    version and, optionally, one current Event Coordinator override on top of it;
    `is_event_coordinator_override` distinguishes the two without needing separate
    tables, and `EvidenceVersion.effective_verification` computes which one
    currently governs without ever mutating either row.
    """

    class Decision(models.TextChoices):
        VERIFIED = 'VERIFIED', 'Verified'
        REJECTED = 'REJECTED', 'Rejected'
        RESUBMISSION_REQUIRED = 'RESUBMISSION_REQUIRED', 'Resubmission Required'

    evidence_version = models.ForeignKey(EvidenceVersion, on_delete=models.PROTECT, related_name='verifications')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    decision = models.CharField(max_length=30, choices=Decision.choices)
    reason = models.TextField(blank=True, default='')
    is_event_coordinator_override = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['created_at']
        constraints = [
            models.CheckConstraint(
                condition=Q(decision='VERIFIED') | ~Q(reason=''),
                name='reason_required_for_reject_or_resubmission',
            ),
        ]

    def __str__(self):
        prefix = 'Event Coordinator override' if self.is_event_coordinator_override else 'Faculty decision'
        return f'{prefix}: {self.decision} on version #{self.evidence_version_id}'
