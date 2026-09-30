"""
Admin user-management serializers.

Kept in their own module rather than added to `serializers.py` because these
are the only serializers in the project that let one user change another
user's account, and that deserves to be easy to find and review as a unit.

Three rules run through all of them:

1. **Nothing sensitive is ever serialized out.** There is no `password`
   field on any read serializer, no password hash, and no token. The write
   serializer accepts a new password but never echoes it back.
2. **Every field a client may change is listed explicitly.** `username`,
   `is_staff`, `is_superuser`, `date_joined` and `last_login` are not
   writable here: a username is an identity other records reference by name
   in the audit trail, and staff/superuser flags are Django-level privileges
   that belong to `createsuperuser` and the Django admin, not to a REST call.
3. **Role changes are validated against the same invariants the database
   enforces**, so a rejected change is a clean `400` rather than an
   `IntegrityError` surfacing as a `500`.
"""

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.departments.models import Department

User = get_user_model()


class _DepartmentBriefSerializer(serializers.Serializer):
    """The department fields a user row needs, declared as a serializer so the
    generated OpenAPI schema describes the object rather than defaulting the
    method field to a bare string."""

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)


class _RegistrationRequestBriefSerializer(serializers.Serializer):
    """The approval history shown on the detail panel."""

    id = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    requested_at = serializers.DateTimeField(read_only=True)
    reviewed_at = serializers.DateTimeField(read_only=True, allow_null=True)
    reviewed_by = serializers.CharField(read_only=True, allow_null=True)
    rejection_reason = serializers.CharField(read_only=True)


class AdminUserListSerializer(serializers.ModelSerializer):
    """One row of the admin user table.

    `department` is nested rather than a bare id so the table can render a
    name without a second request per row (the queryset uses
    `select_related`, so this costs no extra query).
    """

    department = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'full_name', 'role',
            'university_registration_number', 'faculty_id',
            'department', 'is_active', 'is_staff', 'is_superuser',
            'date_joined', 'last_login',
        ]
        read_only_fields = fields

    @extend_schema_field(_DepartmentBriefSerializer(allow_null=True))
    def get_department(self, obj):
        if obj.department_id is None:
            return None
        return {'id': obj.department_id, 'name': obj.department.name, 'code': obj.department.code}

    def get_full_name(self, obj) -> str:
        # The stored field is the source of truth; the inherited first/last
        # pair is only a fallback for accounts created before it existed.
        return obj.full_name or obj.get_full_name()


class AdminUserDetailSerializer(AdminUserListSerializer):
    """The detail view adds the account's approval history, which is the one
    thing a reviewing Admin usually wants that the list cannot show."""

    registration_request = serializers.SerializerMethodField()

    class Meta(AdminUserListSerializer.Meta):
        fields = AdminUserListSerializer.Meta.fields + ['first_name', 'last_name', 'registration_request']
        read_only_fields = fields

    @extend_schema_field(_RegistrationRequestBriefSerializer(allow_null=True))
    def get_registration_request(self, obj):
        request = getattr(obj, 'registration_request', None)
        if request is None:
            return None
        return {
            'id': request.id,
            'status': request.status,
            'requested_at': request.requested_at,
            'reviewed_at': request.reviewed_at,
            'reviewed_by': request.reviewed_by.username if request.reviewed_by_id else None,
            'rejection_reason': request.rejection_reason,
        }


class AdminUserUpdateSerializer(serializers.Serializer):
    """Partial update of the fields an Admin may legitimately change.

    Every field is optional; only what is sent is changed. The cross-field
    rules live in `validate()` because several of them depend on the
    *resulting* combination of role and department rather than on either
    value alone.
    """

    email = serializers.EmailField(required=False)
    full_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    role = serializers.ChoiceField(choices=User.Role.choices, required=False)
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True,
    )
    is_active = serializers.BooleanField(required=False)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError('This email is already registered to another account.')
        return value

    def validate(self, attrs):
        target = self.instance
        actor = self.context['request'].user

        role = attrs.get('role', target.role)
        department = attrs['department'] if 'department' in attrs else target.department
        is_active = attrs.get('is_active', target.is_active)

        # --- role / department coherence ---------------------------------
        if role in (User.Role.STUDENT, User.Role.FACULTY, User.Role.EVENT_COORDINATOR) and department is None:
            raise serializers.ValidationError(
                {'department': 'A %s account must belong to a department.' % role.title()},
            )
        if department is not None and not department.is_active and department != target.department:
            raise serializers.ValidationError(
                {'department': 'That department is inactive and cannot be assigned.'},
            )

        # --- one active Event Coordinator per department -------------------------------
        # The database enforces this with a partial unique index; checking it
        # here turns what would be a 500 from IntegrityError into a clear 400
        # that names the account already holding the post.
        if role == User.Role.EVENT_COORDINATOR and is_active:
            clash = (
                User.objects.filter(role=User.Role.EVENT_COORDINATOR, is_active=True, department=department)
                .exclude(pk=target.pk)
                .first()
            )
            if clash is not None:
                raise serializers.ValidationError({
                    'role': (
                        'Department "%s" already has an active Event Coordinator (%s). Deactivate or reassign that '
                        'account first.' % (department.code, clash.username)
                    ),
                })

        # --- the system must keep a usable Admin -------------------------
        losing_admin = target.role == User.Role.ADMIN and (role != User.Role.ADMIN or not is_active)
        if losing_admin and not self._another_usable_admin_exists(target):
            raise serializers.ValidationError({
                'role': (
                    'This is the only active administrator account. Create or activate another Admin '
                    'before changing or deactivating this one.'
                ),
            })

        # A Django superuser's role is forced back to ADMIN by User.save(),
        # so silently accepting a different role here would be a lie.
        if target.is_superuser and role != User.Role.ADMIN:
            raise serializers.ValidationError({
                'role': 'A Django superuser is always an Admin; its role cannot be changed here.',
            })

        if target.pk == actor.pk and not is_active:
            raise serializers.ValidationError({'is_active': 'You cannot deactivate your own account.'})

        return attrs

    @staticmethod
    def _another_usable_admin_exists(target) -> bool:
        return (
            User.objects.filter(is_active=True)
            .filter(Q(role=User.Role.ADMIN) | Q(is_superuser=True))
            .exclude(pk=target.pk)
            .exists()
        )


class AdminSetPasswordSerializer(serializers.Serializer):
    """Admin-initiated password reset.

    The plaintext arrives, is validated by Django's configured validators,
    is handed to `set_password()` and is then out of scope. It is never
    stored, never logged, never echoed, and the response carries no password
    material at all.
    """

    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        try:
            password_validation.validate_password(attrs['new_password'], user=self.instance)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': list(exc.messages)}) from exc
        return attrs


class AdminUserStatsSerializer(serializers.Serializer):
    """Counts for the header of the user-management page."""

    total = serializers.IntegerField()
    active = serializers.IntegerField()
    inactive = serializers.IntegerField()
    by_role = serializers.DictField(child=serializers.IntegerField())
