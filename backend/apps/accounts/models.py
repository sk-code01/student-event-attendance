from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

username_validator = RegexValidator(
    regex=r'^[a-z0-9]+$',
    message='Username must contain lowercase letters and numbers only.',
)


class User(AbstractUser):
    """
    Custom user model for role-based access control. The frontend is never
    the authority for role/permission decisions — every protected endpoint
    re-checks `role` (see apps.accounts.permissions) on the backend.

    `is_active` doubles as the account-approval flag: STUDENT/FACULTY accounts
    start inactive (is_active=False) until an Event Coordinator/Admin approves their
    RegistrationRequest, at which point Django's own auth backend (and
    therefore JWT login) already refuses inactive users out of the box.
    """

    class Role(models.TextChoices):
        STUDENT = 'STUDENT', 'Student'
        FACULTY = 'FACULTY', 'Faculty'
        EVENT_COORDINATOR = 'EVENT_COORDINATOR', 'Event Coordinator'
        ADMIN = 'ADMIN', 'Admin'

    username = models.CharField(
        max_length=150,
        unique=True,
        validators=[username_validator],
        help_text='Required. Lowercase letters and numbers only.',
        error_messages={'unique': 'This username is already taken.'},
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    email = models.EmailField(unique=True)

    # One authoritative name field rather than AbstractUser's first/last pair:
    # the institutions this serves write a student's name as a single string,
    # and splitting it invents a structure the source data does not have. The
    # inherited fields stay (they come with AbstractUser) but are no longer
    # the source of truth — see the data migration that backfills this from
    # them.
    full_name = models.CharField(
        max_length=150, blank=True, default='',
        help_text="The person's full name as the institution records it.",
    )

    # Institution-issued identifiers. Deliberately free-form: a USN, a UUCMS
    # number and a university registration number have different shapes, and
    # hard-coding one institution's format would reject every other's. They
    # are unique where present, and NULL — never '' — when they do not apply,
    # because Postgres treats each NULL as distinct and would otherwise
    # reject a second user with no identifier.
    university_registration_number = models.CharField(
        max_length=50, unique=True, null=True, blank=True,
        help_text='Student only. USN, UUCMS number, or university registration number.',
    )
    faculty_id = models.CharField(
        max_length=50, unique=True, null=True, blank=True,
        help_text=(
            'Faculty and Event Coordinator. The identifier issued by the college. '
            'Unique across both roles: an Event Coordinator is a faculty member, so '
            'the same person must not be able to hold two identities by changing role.'
        ),
    )
    department = models.ForeignKey(
        'departments.Department',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='users',
    )

    REQUIRED_FIELDS = ['email']

    class Meta:
        constraints = [
            # At most one active Event Coordinator per department, enforced at the
            # database level (a partial unique index), not only in
            # application code or the Angular form.
            models.UniqueConstraint(
                fields=['department'],
                condition=Q(role='EVENT_COORDINATOR', is_active=True),
                name='unique_active_event_coordinator_per_department',
            ),
            # An identifier belongs to exactly the role that issues it, so a
            # Student can never carry a Faculty ID and vice versa. Enforced
            # here as well as in the serializers, because a future admin
            # endpoint or data import would otherwise be able to create the
            # contradiction.
            models.CheckConstraint(
                condition=Q(role='STUDENT') | Q(university_registration_number__isnull=True),
                name='university_registration_number_is_student_only',
            ),
            # Both faculty roles carry the college-issued identifier. An Event
            # Coordinator *is* a faculty member — the role describes what they
            # do in this system, not a different kind of employment — so
            # excluding them here made the identifier unreachable for them and
            # turned every legitimate promotion into a constraint violation.
            models.CheckConstraint(
                condition=(
                    Q(role__in=['FACULTY', 'EVENT_COORDINATOR'])
                    | Q(faculty_id__isnull=True)
                ),
                name='faculty_id_is_faculty_or_coordinator',
            ),
        ]

    def save(self, *args, **kwargs):
        # A Django superuser (e.g. created via createsuperuser) is always
        # system-wide Admin, regardless of what role it was created with.
        if self.is_superuser:
            self.role = self.Role.ADMIN
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.username} ({self.role})'


class RegistrationRequest(models.Model):
    """
    Tracks the approval workflow for self-registered Student/Faculty
    accounts: PENDING -> Event Coordinator review -> APPROVED (activates the linked User)
    or REJECTED (User stays inactive). Event Coordinator/Admin accounts are never created
    through this workflow (see apps.accounts.serializers.RegisterSerializer
    and the provision-event-coordinator endpoint).
    """

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='registration_request')
    role = models.CharField(max_length=20, choices=User.Role.choices)
    department = models.ForeignKey(
        'departments.Department', on_delete=models.PROTECT, related_name='registration_requests',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name='reviewed_registration_requests',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-requested_at']
        constraints = [
            # Self-registration only ever produces STUDENT/FACULTY requests;
            # Event Coordinator/Admin provisioning is a separate, authorized-only path.
            models.CheckConstraint(
                condition=Q(role__in=[User.Role.STUDENT, User.Role.FACULTY]),
                name='registration_request_role_must_be_student_or_faculty',
            ),
        ]

    def __str__(self):
        return f'{self.user.username} -> {self.role} ({self.status})'
