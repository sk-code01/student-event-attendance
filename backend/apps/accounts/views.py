from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.audit.models import AuditLog
from apps.notifications import services as notifications

from .models import RegistrationRequest
from .permissions import IsAdminRole, IsEventCoordinatorOrAdmin
from .serializers import (
    ChangePasswordSerializer,
    EventCoordinatorProvisionSerializer,
    RegisterSerializer,
    RegistrationRequestSerializer,
    RegistrationStatusSerializer,
    RoleAwareTokenObtainPairSerializer,
    UserSerializer,
)


class _RefreshTokenInputSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class _GenericDetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """Public self-registration.

    Student and Faculty accounts stay inactive until an Event Coordinator
    approves the linked RegistrationRequest. An Event Coordinator registers
    themselves and is active immediately, so no request is created and the
    response says so rather than telling them to wait for an approval that
    will never come.
    """

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        registration_request = RegistrationRequest.objects.filter(user=user).first()
        if registration_request is not None:
            notifications.schedule(
                notifications.notify_registration_submitted, registration_request=registration_request,
            )
            detail = 'Registration submitted. Your account is pending Event Coordinator approval.'
        else:
            detail = 'Registration complete. You can sign in now.'
        return Response(
            {
                'detail': detail,
                'user': UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class RoleAwareTokenObtainPairView(TokenObtainPairView):
    serializer_class = RoleAwareTokenObtainPairSerializer
    throttle_scope = 'auth'


class LogoutView(APIView):
    """Blacklists the supplied refresh token. The access token remains valid
    until it naturally expires (short-lived by design); clients must discard
    it locally on logout."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=_RefreshTokenInputSerializer, responses={205: None})
    def post(self, request):
        refresh = request.data.get('refresh')
        if not refresh:
            return Response({'refresh': 'This field is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except TokenError:
            return Response({'detail': 'Invalid or expired refresh token.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(generics.RetrieveAPIView):
    """The authoritative source of the current user's identity and role —
    Angular must treat this (not a decoded JWT) as the source of truth for
    what to render."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer, responses=_GenericDetailSerializer)
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.check_password(serializer.validated_data['old_password']):
            return Response({'old_password': 'Incorrect current password.'}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])

        # Force re-authentication everywhere: blacklist every outstanding
        # refresh token issued to this user before the password change.
        outstanding_ids = OutstandingToken.objects.filter(user=user).values_list('id', flat=True)
        already_blacklisted = set(
            BlacklistedToken.objects.filter(token_id__in=outstanding_ids).values_list('token_id', flat=True)
        )
        for outstanding in OutstandingToken.objects.filter(id__in=outstanding_ids).exclude(id__in=already_blacklisted):
            BlacklistedToken.objects.create(token=outstanding)

        return Response({'detail': 'Password changed successfully.'})


class RegistrationStatusView(APIView):
    """Lets a not-yet-active applicant check their approval status without
    being able to log in (their account is inactive by design)."""

    permission_classes = [AllowAny]
    throttle_scope = 'auth'

    @extend_schema(
        request=RegistrationStatusSerializer,
        responses={200: OpenApiResponse(description='Registration request status.')},
    )
    def post(self, request):
        serializer = RegistrationStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data['username']

        try:
            registration_request = RegistrationRequest.objects.select_related('user').get(
                user__username=username,
            )
        except RegistrationRequest.DoesNotExist:
            return Response(
                {'detail': 'No registration request found for this username.'}, status=status.HTTP_404_NOT_FOUND,
            )

        payload = {
            'status': registration_request.status,
            'requested_at': registration_request.requested_at,
        }
        if registration_request.status == RegistrationRequest.Status.REJECTED:
            payload['rejection_reason'] = registration_request.rejection_reason
        return Response(payload)


class RegistrationRequestListView(generics.ListAPIView):
    """Event Coordinator sees only their own department's requests; Admin sees all."""

    serializer_class = RegistrationRequestSerializer
    permission_classes = [IsEventCoordinatorOrAdmin]

    def get_queryset(self):
        queryset = RegistrationRequest.objects.select_related('user', 'department', 'reviewed_by')
        user = self.request.user
        if user.role == User.Role.EVENT_COORDINATOR and not user.is_superuser:
            queryset = queryset.filter(department_id=user.department_id)
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset = queryset.filter(status=status_param.upper())
        return queryset


class _RegistrationRequestActionView(APIView):
    permission_classes = [IsEventCoordinatorOrAdmin]

    def get_scoped_object(self, request, pk):
        obj = get_object_or_404(RegistrationRequest, pk=pk)
        user = request.user
        if (
            user.role == User.Role.EVENT_COORDINATOR
            and not user.is_superuser
            and obj.department_id != user.department_id
        ):
            raise PermissionDenied('You can only review registration requests for your own department.')
        return obj


class RegistrationRequestApproveView(_RegistrationRequestActionView):
    @extend_schema(request=None, responses=RegistrationRequestSerializer)
    def post(self, request, pk):
        registration_request = self.get_scoped_object(request, pk)
        if registration_request.status != RegistrationRequest.Status.PENDING:
            return Response({'detail': 'This request has already been reviewed.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            registration_request.status = RegistrationRequest.Status.APPROVED
            registration_request.reviewed_by = request.user
            registration_request.reviewed_at = timezone.now()
            registration_request.save()

            registration_request.user.is_active = True
            registration_request.user.save(update_fields=['is_active'])

            # Phase 1 recorded no audit entry for this decision. Event Coordinator activity
            # (Phase 6) is derived from AuditLog, so approvals would otherwise
            # be invisible there. The approval logic itself is unchanged.
            AuditLog.record(
                actor=request.user, action='REGISTRATION_REQUEST_APPROVED',
                description=f'Registration request #{registration_request.id} approved for '
                            f'{registration_request.user.username}.',
            )
            notifications.schedule(
                notifications.notify_registration_decision, registration_request=registration_request,
            )

        return Response(RegistrationRequestSerializer(registration_request).data)


class RegistrationRequestRejectView(_RegistrationRequestActionView):
    @extend_schema(request=None, responses=RegistrationRequestSerializer)
    def post(self, request, pk):
        registration_request = self.get_scoped_object(request, pk)
        if registration_request.status != RegistrationRequest.Status.PENDING:
            return Response({'detail': 'This request has already been reviewed.'}, status=status.HTTP_400_BAD_REQUEST)

        reason = (request.data.get('rejection_reason') or '').strip()
        if not reason:
            return Response({'rejection_reason': 'A rejection reason is required.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            registration_request.status = RegistrationRequest.Status.REJECTED
            registration_request.reviewed_by = request.user
            registration_request.reviewed_at = timezone.now()
            registration_request.rejection_reason = reason
            registration_request.save()
            AuditLog.record(
                actor=request.user, action='REGISTRATION_REQUEST_REJECTED',
                description=f'Registration request #{registration_request.id} rejected for '
                            f'{registration_request.user.username}.',
            )
            notifications.schedule(
                notifications.notify_registration_decision, registration_request=registration_request,
            )

        return Response(RegistrationRequestSerializer(registration_request).data)


class EventCoordinatorProvisionView(generics.CreateAPIView):
    """Admin-only. Creates an immediately-active Event Coordinator, since the first Event Coordinator of
    a department cannot depend on another Event Coordinator's approval."""

    serializer_class = EventCoordinatorProvisionSerializer
    permission_classes = [IsAdminRole]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
