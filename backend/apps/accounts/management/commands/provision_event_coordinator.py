from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import username_validator
from apps.departments.models import Department

User = get_user_model()


class Command(BaseCommand):
    """CLI bootstrap for a department's first Event Coordinator, since an Event Coordinator cannot
    depend on another Event Coordinator's approval. Equivalent to the admin-only
    /api/v1/users/provision-event-coordinator/ endpoint, usable before any Admin exists."""

    help = "Provision an active Event Coordinator for a department, bypassing the approval workflow."

    def add_arguments(self, parser):
        parser.add_argument('--username', required=True)
        parser.add_argument('--email', required=True)
        parser.add_argument('--password', required=True)
        parser.add_argument('--department', required=True, help='Department code')
        parser.add_argument('--full-name', default='', help="The coordinator's full name.")
        parser.add_argument(
            '--faculty-id', default='',
            help="The college-issued Faculty ID. Optional: leave it out rather than inventing one.",
        )

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']
        department_code = options['department']

        try:
            username_validator(username)
        except DjangoValidationError as exc:
            raise CommandError('; '.join(exc.messages))

        if User.objects.filter(username=username).exists():
            raise CommandError(f'Username "{username}" is already taken.')
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError(f'Email "{email}" is already registered.')

        try:
            department = Department.objects.get(code=department_code)
        except Department.DoesNotExist:
            raise CommandError(f'No department with code "{department_code}" exists.')

        if User.objects.filter(department=department, role=User.Role.EVENT_COORDINATOR, is_active=True).exists():
            raise CommandError(f'Department "{department.code}" already has an active Event Coordinator.')

        try:
            password_validation.validate_password(password)
        except DjangoValidationError as exc:
            raise CommandError('; '.join(exc.messages))

        faculty_id = (options.get('faculty_id') or '').strip().lower() or None
        if faculty_id and User.objects.filter(faculty_id__iexact=faculty_id).exists():
            raise CommandError(f'Faculty ID "{faculty_id}" is already registered.')

        user = User(
            username=username, email=email, full_name=(options.get('full_name') or '').strip(),
            role=User.Role.EVENT_COORDINATOR, department=department, is_active=True,
            faculty_id=faculty_id,
        )
        user.set_password(password)
        user.save()

        self.stdout.write(self.style.SUCCESS(
            f'Event Coordinator "{user.username}" provisioned for department "{department.code}".'
        ))
