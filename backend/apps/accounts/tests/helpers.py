from django.contrib.auth import get_user_model

from apps.departments.models import Department

User = get_user_model()

DEFAULT_PASSWORD = 'StrongPass123!'


def make_department(code='CS', name='Computer Science', is_active=True):
    return Department.objects.create(code=code, name=name, is_active=is_active)


def make_user(
    username,
    role=User.Role.STUDENT,
    department=None,
    is_active=True,
    password=DEFAULT_PASSWORD,
    email=None,
    full_name=None,
    university_registration_number=None,
    faculty_id=None,
):
    """Creates a user with identity fields that satisfy the role constraints.

    The identifiers default to values derived from the username so every
    fixture is unique without each test having to invent one, and they are
    left NULL for the roles that must not carry them — the database refuses
    a Student with a Faculty ID and vice versa.
    """
    if role == User.Role.STUDENT and university_registration_number is None:
        university_registration_number = f'USN{username.upper()}'
    if role == User.Role.FACULTY and faculty_id is None:
        faculty_id = f'fid{username.lower()}'

    user = User(
        username=username,
        email=email or f'{username}@example.com',
        full_name=full_name if full_name is not None else username.title(),
        role=role,
        department=department,
        is_active=is_active,
        university_registration_number=(
            university_registration_number if role == User.Role.STUDENT else None
        ),
        faculty_id=faculty_id if role == User.Role.FACULTY else None,
    )
    user.set_password(password)
    user.save()
    return user


def make_admin(username='admin1', password=DEFAULT_PASSWORD):
    return make_user(username, role=User.Role.ADMIN, department=None, is_active=True, password=password)


def make_event_coordinator(username, department, password=DEFAULT_PASSWORD, faculty_id=None):
    # `faculty_id` defaults to None so the many existing callers that do not
    # care about the identifier keep working: it is required at registration,
    # not at the database level, because an account provisioned by an Admin may
    # legitimately not have one recorded yet.
    return make_user(
        username, role=User.Role.EVENT_COORDINATOR, department=department,
        is_active=True, password=password, faculty_id=faculty_id,
    )


def make_faculty(username, department, is_active=True, password=DEFAULT_PASSWORD, faculty_id=None):
    return make_user(
        username, role=User.Role.FACULTY, department=department, is_active=is_active,
        password=password, faculty_id=faculty_id,
    )


def make_student(username, department, is_active=True, password=DEFAULT_PASSWORD,
                 university_registration_number=None):
    return make_user(
        username, role=User.Role.STUDENT, department=department, is_active=is_active,
        password=password, university_registration_number=university_registration_number,
    )
