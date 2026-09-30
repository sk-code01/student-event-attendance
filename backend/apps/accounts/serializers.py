from django.contrib.auth import get_user_model
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.departments.models import Department
from apps.departments.serializers import DepartmentSerializer

from .models import RegistrationRequest, username_validator

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """The authoritative representation of 'who am I' returned by /users/me/.
    Never includes the password hash or any write-only credential field."""

    department = DepartmentSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'full_name', 'role', 'department',
            'university_registration_number', 'faculty_id', 'is_active', 'date_joined',
        ]
        read_only_fields = fields


class RegisterSerializer(serializers.Serializer):
    """Public self-registration.

    Three roles register here and they do not follow the same path. Student
    and Faculty accounts are created inactive and wait for an Event
    Coordinator to approve the RegistrationRequest. An Event Coordinator
    registers themselves and is active immediately — there is nobody above
    them in the department to approve it — subject to the rule that a
    department has at most one. Admin can never be created here at all: the
    role choices exclude it at field level rather than by a runtime check.
    """

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150, trim_whitespace=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)
    role = serializers.ChoiceField(
        choices=[User.Role.STUDENT, User.Role.FACULTY, User.Role.EVENT_COORDINATOR],
    )
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.filter(is_active=True))

    # Required for exactly one role each. Enforced in `validate` rather than
    # with `required=True`, because a field-level rule cannot see the role
    # that was submitted alongside it.
    university_registration_number = serializers.CharField(
        max_length=50, required=False, allow_blank=True, trim_whitespace=True,
        help_text=(
            'Required when role is STUDENT, and rejected for every other role. '
            'The University Registration Number, USN or UUCMS number — one field for '
            'all three, since they are three names for the same value. No format is '
            'imposed. Unique across students; matched case-insensitively and stored '
            'upper-cased.'
        ),
    )
    faculty_id = serializers.CharField(
        max_length=50, required=False, allow_blank=True, trim_whitespace=True,
        help_text=(
            'Required when role is FACULTY or EVENT_COORDINATOR, and rejected for every '
            'other role. An Event Coordinator is a faculty member, so both roles are '
            'issued the same college identifier. Unique across all users rather than '
            'within a role, so one person cannot hold two identities by registering '
            'under each faculty role. Matched case-insensitively and stored lowercase.'
        ),
    )

    def validate_username(self, value):
        try:
            username_validator(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('This username is already taken.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('This email is already registered.')
        return value

    def validate_full_name(self, value):
        if not value.strip():
            raise serializers.ValidationError('Full name is required.')
        return value.strip()

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        try:
            password_validation.validate_password(attrs['password'])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages}) from exc

        role = attrs['role']
        usn = (attrs.get('university_registration_number') or '').strip()
        faculty_id = (attrs.get('faculty_id') or '').strip()

        if role == User.Role.STUDENT:
            if not usn:
                raise serializers.ValidationError({
                    'university_registration_number': 'University registration number is required.',
                })
            if faculty_id:
                raise serializers.ValidationError({'faculty_id': 'Only Faculty accounts carry a Faculty ID.'})
            # No format is imposed: a USN, a UUCMS number and a university
            # registration number have different shapes, and hard-coding one
            # institution's pattern would reject every other institution's.
            # Case is normalised because these identifiers are written both
            # ways and mean the same person.
            if User.objects.filter(university_registration_number__iexact=usn).exists():
                raise serializers.ValidationError({
                    'university_registration_number': 'This university registration number is already registered.',
                })
            attrs['university_registration_number'] = usn.upper()
            attrs['faculty_id'] = None

        else:
            # Faculty and Event Coordinator alike. An Event Coordinator is a
            # faculty member — the role describes what they do in this system,
            # not a different kind of employment — so both are issued, and both
            # must supply, the college's Faculty ID.
            if not faculty_id:
                raise serializers.ValidationError({'faculty_id': 'Faculty ID is required.'})
            if usn:
                raise serializers.ValidationError({
                    'university_registration_number': 'Only Student accounts carry a university registration number.',
                })
            # Checked across every user rather than within the role: otherwise
            # one faculty member could hold a second account under the other
            # faculty role with the same identifier, which is the duplicate
            # identity this is meant to prevent.
            if User.objects.filter(faculty_id__iexact=faculty_id).exists():
                raise serializers.ValidationError({'faculty_id': 'This Faculty ID is already registered.'})
            attrs['faculty_id'] = faculty_id.lower()
            attrs['university_registration_number'] = None

        if role == User.Role.EVENT_COORDINATOR:
            # Unchanged: one active Event Coordinator per department. Checked
            # here so the caller gets a clear message; the database also
            # refuses it via unique_active_event_coordinator_per_department,
            # which is what actually holds when two registrations race.
            if User.objects.filter(
                role=User.Role.EVENT_COORDINATOR, is_active=True, department=attrs['department'],
            ).exists():
                raise serializers.ValidationError({
                    'department': 'This department already has an active Event Coordinator.',
                })

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop('confirm_password')
        password = validated_data.pop('password')
        role = validated_data['role']
        # An Event Coordinator has no approver above them in the department,
        # so the account is usable at once; Student and Faculty stay inactive
        # until an Event Coordinator approves the request.
        is_event_coordinator = role == User.Role.EVENT_COORDINATOR

        user = User(
            username=validated_data['username'],
            email=validated_data['email'],
            full_name=validated_data['full_name'],
            role=role,
            department=validated_data['department'],
            university_registration_number=validated_data.get('university_registration_number') or None,
            faculty_id=validated_data.get('faculty_id') or None,
            is_active=is_event_coordinator,
        )
        user.set_password(password)
        try:
            user.save()
        except IntegrityError as exc:
            # The unique index lost the race: report it as the validation
            # failure it is, rather than as a 500.
            raise serializers.ValidationError({
                'department': 'This department already has an active Event Coordinator.',
            }) from exc

        if not is_event_coordinator:
            RegistrationRequest.objects.create(
                user=user,
                role=user.role,
                department=user.department,
            )
        return user


class RegistrationRequestSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)
    reviewed_by = serializers.StringRelatedField()

    class Meta:
        model = RegistrationRequest
        fields = [
            'id', 'user', 'role', 'department', 'status',
            'requested_at', 'reviewed_by', 'reviewed_at', 'rejection_reason',
        ]
        read_only_fields = fields


class RegistrationStatusSerializer(serializers.Serializer):
    username = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError({'confirm_new_password': 'Passwords do not match.'})
        try:
            password_validation.validate_password(attrs['new_password'], user=self.context['request'].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': exc.messages}) from exc
        return attrs


class EventCoordinatorProvisionSerializer(serializers.Serializer):
    """Admin-only: creates an active Event Coordinator immediately, bypassing the
    Student/Faculty approval workflow entirely (an Event Coordinator cannot depend on
    another Event Coordinator's approval)."""

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    # Optional here, unlike self-registration: an Admin provisioning an account
    # may not know the person's full name yet, and blocking the provisioning on
    # it would be worse than recording it later.
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)
    department = serializers.PrimaryKeyRelatedField(queryset=Department.objects.filter(is_active=True))
    # Optional for the same reason as `full_name`: an Admin provisioning the
    # account may not have the college's Faculty ID to hand, and an identifier
    # must never be invented to fill a required field. Validated when supplied.
    faculty_id = serializers.CharField(
        max_length=50, required=False, allow_blank=True, trim_whitespace=True,
    )

    def validate_username(self, value):
        try:
            username_validator(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('This username is already taken.')
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('This email is already registered.')
        return value

    def validate_faculty_id(self, value):
        faculty_id = (value or '').strip()
        if not faculty_id:
            return None
        # Across every user, not within the role: an Event Coordinator is a
        # faculty member, so the same identifier must not be usable twice by
        # switching role.
        if User.objects.filter(faculty_id__iexact=faculty_id).exists():
            raise serializers.ValidationError('This Faculty ID is already registered.')
        return faculty_id.lower()

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        try:
            password_validation.validate_password(attrs['password'])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': exc.messages}) from exc

        department = attrs['department']
        if User.objects.filter(
            department=department, role=User.Role.EVENT_COORDINATOR, is_active=True,
        ).exists():
            raise serializers.ValidationError({
                'department': 'This department already has an active Event Coordinator.',
            })
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop('confirm_password')
        password = validated_data.pop('password')
        user = User(
            username=validated_data['username'],
            email=validated_data['email'],
            full_name=(validated_data.get('full_name') or '').strip(),
            role=User.Role.EVENT_COORDINATOR,
            department=validated_data['department'],
            # NULL rather than '': the column is unique, and Postgres treats
            # each NULL as distinct while a second '' would collide.
            faculty_id=validated_data.get('faculty_id') or None,
            is_active=True,
        )
        user.set_password(password)
        user.save()
        return user


class RoleAwareTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds role/department claims to the token and distinguishes
    invalid-credentials from pending/rejected/inactive account states, per
    the project's error-handling requirements."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['department_id'] = user.department_id
        return token

    def validate(self, attrs):
        username = attrs.get(self.username_field)
        candidate = User.objects.filter(**{self.username_field: username}).first()

        if candidate is not None and not candidate.is_active:
            # Match SimpleJWT's own 401 for "cannot log in" outcomes, rather
            # than the 400 a plain ValidationError would produce — from the
            # client's perspective this is still an authentication failure,
            # just with a more specific reason than bad credentials.
            registration_request = getattr(candidate, 'registration_request', None)
            if registration_request and registration_request.status == RegistrationRequest.Status.PENDING:
                raise AuthenticationFailed(
                    'Your account is pending Event Coordinator approval.', code='account_pending',
                )
            if registration_request and registration_request.status == RegistrationRequest.Status.REJECTED:
                raise AuthenticationFailed('Your registration request was rejected.', code='account_rejected')
            raise AuthenticationFailed('This account has been deactivated.', code='account_inactive')

        return super().validate(attrs)


class PersonBriefSerializer(serializers.Serializer):
    """
    A minimal, non-sensitive identity block for embedding a requester/reviewer
    inside another app's response (attendance, OD, achievements). Defined once
    here — accounts owns the User model — rather than re-declared per app,
    which would otherwise produce several identically-shaped OpenAPI
    components with the same name.

    Read-only by construction: it is only ever used to describe output, never
    to accept a client-supplied identity.
    """

    id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    department = serializers.CharField(read_only=True, allow_null=True, required=False)


def person_brief(user, *, include_department: bool = False):
    """Serializes a user into the PersonBriefSerializer shape, or None."""
    if user is None:
        return None
    data = {'id': user.id, 'username': user.username, 'role': user.role}
    if include_department:
        data['department'] = user.department.name if user.department_id else None
    return data
