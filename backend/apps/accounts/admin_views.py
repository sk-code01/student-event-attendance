"""
Admin user management.

Every view here is `IsAdminRole` — system-wide by definition, which is why
these are the endpoints most worth keeping together and auditing as a set.
An Event Coordinator reviews registration requests for their own department through
`registration-requests/`; that is a different, narrower capability and is
deliberately not merged into this one.

Four properties hold across the module:

* **Admin-only, server-enforced.** The Angular route guard is UX; the
  permission class is the boundary.
* **Every mutation is audited** with the actor, the target and what changed —
  ids, usernames, roles and field names, never a password or a token.
* **Every mutation is atomic**, so a change and its audit entry either both
  land or neither does.
* **Nothing sensitive is serialized out.** No password, no hash, no token.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.audit.models import AuditLog

from .admin_serializers import (
    AdminSetPasswordSerializer,
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AdminUserStatsSerializer,
    AdminUserUpdateSerializer,
)
from .permissions import IsAdminRole

User = get_user_model()


def _base_queryset():
    """`select_related('department')` is what keeps the list a fixed number of
    queries: the row serializer reads `department.name`/`code`, which would
    otherwise be one query per row."""
    return User.objects.select_related('department').order_by('username')


@extend_schema(
    parameters=[
        OpenApiParameter(
            'search', str,
            description=(
                'Matches username, email, full name, university registration number '
                'or Faculty ID (case-insensitive).'
            ),
        ),
        OpenApiParameter('role', str, description='STUDENT | FACULTY | Event Coordinator | ADMIN.'),
        OpenApiParameter('department', int, description='Department id. Use "none" for accounts with no department.'),
        OpenApiParameter('status', str, description='active | inactive | all (default all).'),
        OpenApiParameter('ordering', str, description='username | email | role | date_joined (prefix "-" to reverse).'),
    ],
    responses=AdminUserListSerializer(many=True), tags=['admin-users'],
)
class AdminUserListView(generics.ListAPIView):
    """Paginated, searchable, filterable list of every account.

    Filtering happens in the database, never in Python, so the cost of this
    endpoint does not grow with the number of accounts that are filtered out.
    """

    serializer_class = AdminUserListSerializer
    permission_classes = [IsAdminRole]

    ORDERING_FIELDS = {'username', 'email', 'role', 'date_joined', 'is_active'}

    def get_queryset(self):
        queryset = _base_queryset()
        params = self.request.query_params

        search = (params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(full_name__icontains=search)
                # The institution-issued identifiers are how staff actually
                # look a person up, so they are searchable too.
                | Q(university_registration_number__icontains=search)
                | Q(faculty_id__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search),
            )

        role = (params.get('role') or '').strip().upper()
        if role:
            # An unknown role yields an empty page rather than every account:
            # silently ignoring an unrecognised filter would show the operator
            # more than they asked for.
            queryset = queryset.filter(role=role)

        department = (params.get('department') or '').strip()
        if department.lower() == 'none':
            queryset = queryset.filter(department__isnull=True)
        elif department:
            if not department.isdigit():
                return queryset.none()
            queryset = queryset.filter(department_id=int(department))

        account_status = (params.get('status') or 'all').strip().lower()
        if account_status == 'active':
            queryset = queryset.filter(is_active=True)
        elif account_status == 'inactive':
            queryset = queryset.filter(is_active=False)

        ordering = (params.get('ordering') or '').strip()
        if ordering.lstrip('-') in self.ORDERING_FIELDS:
            queryset = queryset.order_by(ordering)

        return queryset


@extend_schema(responses=AdminUserStatsSerializer, tags=['admin-users'])
class AdminUserStatsView(APIView):
    """Header counts for the user-management page.

    Separate from the list so pagination keeps its ordinary meaning — putting
    whole-table totals inside a page of results would make `count` ambiguous.
    It is three aggregates in one query plus one grouped query, independent of
    how many accounts exist.
    """

    permission_classes = [IsAdminRole]

    def get(self, request):
        totals = User.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(is_active=True)),
            inactive=Count('id', filter=Q(is_active=False)),
        )
        by_role = {row['role']: row['n'] for row in User.objects.values('role').annotate(n=Count('id'))}
        return Response(AdminUserStatsSerializer({
            'total': totals['total'],
            'active': totals['active'],
            'inactive': totals['inactive'],
            'by_role': {role: by_role.get(role, 0) for role, _ in User.Role.choices},
        }).data)


@extend_schema(tags=['admin-users'])
class AdminUserDetailView(generics.RetrieveUpdateAPIView):
    """Read one account, or change the fields an Admin may change.

    `PUT` is not offered — a full replace would invite a client to send a
    stale copy of every field. Only `PATCH` is accepted, and it applies
    exactly what was sent.
    """

    permission_classes = [IsAdminRole]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_queryset(self):
        return _base_queryset().select_related('registration_request__reviewed_by')

    def get_serializer_class(self):
        return AdminUserUpdateSerializer if self.request.method == 'PATCH' else AdminUserDetailSerializer

    @extend_schema(request=AdminUserUpdateSerializer, responses=AdminUserDetailSerializer)
    def patch(self, request, *args, **kwargs):
        target = self.get_object()
        serializer = AdminUserUpdateSerializer(
            instance=target, data=request.data, partial=True, context={'request': request},
        )
        serializer.is_valid(raise_exception=True)

        changes = []
        with transaction.atomic():
            # Re-read under a row lock so two concurrent Admins cannot both
            # pass the "one active Event Coordinator" check and then both write.
            target = User.objects.select_for_update().get(pk=target.pk)
            for field, value in serializer.validated_data.items():
                previous = getattr(target, field)
                if previous == value:
                    continue
                setattr(target, field, value)
                changes.append('%s: %s -> %s' % (field, _display(previous), _display(value)))

            # An institution-issued identifier belongs to the roles it is
            # issued to, so a role change drops one that no longer applies —
            # and keeps one that still does. Both faculty roles carry the
            # Faculty ID, so promoting a Faculty member to Event Coordinator
            # preserves it: they are the same person, holding the same
            # college-issued identifier, doing different work. Dropping it
            # there would discard real institutional data.
            for field, owning_roles in (
                ('university_registration_number', {User.Role.STUDENT}),
                ('faculty_id', {User.Role.FACULTY, User.Role.EVENT_COORDINATOR}),
            ):
                if target.role not in owning_roles and getattr(target, field) is not None:
                    changes.append('%s: %s -> none' % (field, _display(getattr(target, field))))
                    setattr(target, field, None)

            if changes:
                # The serializer has already rejected every invariant
                # violation it can see, but two concurrent promotions to Event Coordinator
                # in the same department can each pass that check and only
                # collide at the database's partial unique index. Catching it
                # here turns the loser of that race into a clean 400 instead
                # of an IntegrityError surfacing as a 500.
                try:
                    target.full_clean(exclude=['password'])
                    target.save()
                except (DjangoValidationError, IntegrityError) as exc:
                    raise serializers.ValidationError(
                        {'detail': _constraint_message(exc)},
                    ) from exc

                AuditLog.record(
                    actor=request.user,
                    action='ADMIN_USER_UPDATED',
                    description='Admin %s updated user %s (#%s): %s'
                                % (request.user.username, target.username, target.pk, '; '.join(changes)),
                )

        target = self.get_queryset().get(pk=target.pk)
        return Response(AdminUserDetailSerializer(target).data)


class _AdminUserActivationView(APIView):
    """Shared body for activate/deactivate, which differ only in the target
    value and in which invariants can be violated."""

    permission_classes = [IsAdminRole]
    activate = True

    def post(self, request, pk):
        target = generics.get_object_or_404(_base_queryset(), pk=pk)

        if target.is_active == self.activate:
            return Response(
                {'detail': 'This account is already %s.' % ('active' if self.activate else 'inactive')},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AdminUserUpdateSerializer(
            instance=target, data={'is_active': self.activate}, partial=True, context={'request': request},
        )
        # Reuse the update serializer so activation obeys exactly the same
        # invariants as an edit: no second, drifting copy of "one active Event Coordinator
        # per department" or "keep one usable Admin".
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            target = User.objects.select_for_update().get(pk=target.pk)
            target.is_active = self.activate
            target.save(update_fields=['is_active'])
            AuditLog.record(
                actor=request.user,
                action='ADMIN_USER_ACTIVATED' if self.activate else 'ADMIN_USER_DEACTIVATED',
                description='Admin %s %s user %s (#%s).'
                            % (request.user.username,
                               'activated' if self.activate else 'deactivated',
                               target.username, target.pk),
            )

        target = _base_queryset().get(pk=target.pk)
        return Response(AdminUserDetailSerializer(target).data)


@extend_schema(request=None, responses=AdminUserDetailSerializer, tags=['admin-users'])
class AdminUserActivateView(_AdminUserActivationView):
    activate = True


@extend_schema(request=None, responses=AdminUserDetailSerializer, tags=['admin-users'])
class AdminUserDeactivateView(_AdminUserActivationView):
    """Deactivation is the off switch, never deletion: the account stops
    working immediately (Django's auth backend refuses inactive users, so
    existing access tokens stop authenticating too) while every record it
    created stays attributable."""

    activate = False


@extend_schema(
    request=AdminSetPasswordSerializer,
    responses={200: OpenApiResponse(description='Password reset. No password material is returned.')},
    tags=['admin-users'],
)
class AdminUserSetPasswordView(APIView):
    """Admin-initiated password reset.

    `set_password()` hashes with Django's configured hasher; the plaintext is
    never stored, never logged and never returned. The response says only
    that it succeeded.
    """

    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        target = generics.get_object_or_404(User, pk=pk)
        serializer = AdminSetPasswordSerializer(instance=target, data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            target = User.objects.select_for_update().get(pk=target.pk)
            target.set_password(serializer.validated_data['new_password'])
            target.save(update_fields=['password'])

            # A reset exists to take an account back under control, so the
            # sessions it may already have been compromised through must not
            # survive it. Blacklisting the outstanding refresh tokens ends
            # them; the short-lived access tokens expire on their own.
            revoked = _blacklist_refresh_tokens(target)

            AuditLog.record(
                actor=request.user,
                action='ADMIN_PASSWORD_RESET',
                description='Admin %s reset the password for user %s (#%s); %d refresh token(s) revoked.'
                            % (request.user.username, target.username, target.pk, revoked),
            )

        return Response({
            'detail': 'Password updated. The user must sign in again with the new password.',
            'sessions_revoked': revoked,
        })


def _blacklist_refresh_tokens(user) -> int:
    """Blacklist every outstanding refresh token for `user`.

    The blacklist app is already in INSTALLED_APPS (refresh rotation depends
    on it), so its models are imported at module level like any other.
    Returns how many tokens were newly blacklisted.
    """
    count = 0
    for token in OutstandingToken.objects.filter(user=user):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        if created:
            count += 1
    return count


def _constraint_message(exc) -> str:
    """A safe, human message for a database-level constraint collision.

    The raw exception text names the index and the table, which is internal
    detail; the one constraint a concurrent Admin edit can realistically hit
    is the single-active-Event Coordinator index, so that is named explicitly and anything
    else falls back to a generic retry message.
    """
    text = str(exc)
    if 'unique_active_event_coordinator_per_department' in text:
        return (
            'That department already has an active Event Coordinator. Another administrator may have just '
            'assigned one; reload and try again.'
        )
    return 'That change conflicts with another recent change. Reload and try again.'


def _display(value):
    """Audit-friendly rendering. Model instances become their code/name
    rather than a repr, and None becomes a readable dash."""
    if value is None:
        return '-'
    code = getattr(value, 'code', None)
    if code is not None:
        return code
    return str(value)
