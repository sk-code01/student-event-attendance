from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsStudent
from apps.audit.models import AuditLog

from .models import Registration
from .permissions import CanAccessRegistration
from .serializers import (
    RegistrationCreateSerializer,
    RegistrationSerializer,
    TrackingRowSerializer,
)
from .tracking import apply_row_filters, build_row, tracking_queryset


class RegistrationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Deliberately not a full ModelViewSet: registrations are never edited or
    hard-deleted through the API — only created and cancelled (a dedicated
    action, since cancellation is a status transition with its own rules,
    not a generic PATCH).
    """

    queryset = Registration.objects.select_related(
        'student', 'event', 'event__conducting_college', 'event__created_by', 'event__department',
    )
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return RegistrationCreateSerializer
        return RegistrationSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated(), IsStudent()]
        if self.action in ('retrieve', 'cancel'):
            return [IsAuthenticated(), CanAccessRegistration()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()

        if user.is_superuser or user.role == user.Role.ADMIN:
            scoped = queryset
        elif user.role == user.Role.EVENT_COORDINATOR:
            scoped = queryset.filter(event__department_id=user.department_id)
        elif user.role == user.Role.STUDENT:
            scoped = queryset.filter(student=user)
        elif user.role == user.Role.FACULTY:
            # Faculty verify evidence for their department's events, so they
            # need to see who registered for them. Same department scope as
            # the Event Coordinator; the difference between the two roles is
            # what they may *do*, not what they may see.
            scoped = queryset.filter(event__department_id=user.department_id)
        else:
            scoped = queryset.none()

        event_id = self.request.query_params.get('event')
        if event_id:
            # A non-numeric id is a client error, not a server one: without
            # this guard the ORM raises ValueError and the request 500s.
            if not str(event_id).isdigit():
                raise ValidationError({'event': 'Expected a numeric event id.'})
            scoped = scoped.filter(event_id=int(event_id))
        return scoped

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.validated_data['event']

        try:
            # One transaction for the row and its audit record: a failure in
            # either leaves neither behind.
            with transaction.atomic():
                registration = Registration.objects.create(student=request.user, event=event)
                AuditLog.record(
                    actor=request.user, action='EVENT_REGISTERED',
                    description=f'Student #{request.user.id} registered for event #{event.id} "{event.title}".',
                )
        except IntegrityError:
            raise ValidationError({'event': 'You are already registered for this event.'})
        return Response(
            RegistrationSerializer(registration, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=None, responses=RegistrationSerializer)
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        registration = self.get_object()

        is_admin = request.user.is_superuser or request.user.role == request.user.Role.ADMIN
        if not (is_admin or registration.student_id == request.user.id):
            raise PermissionDenied('You can only cancel your own registration.')

        if registration.status == Registration.Status.CANCELLED:
            return Response({'detail': 'This registration is already cancelled.'}, status=status.HTTP_400_BAD_REQUEST)
        if registration.event.event_date < timezone.localdate():
            return Response(
                {'detail': 'Cannot cancel a registration for an event that has already occurred.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            registration.status = Registration.Status.CANCELLED
            registration.cancelled_at = timezone.now()
            registration.save(update_fields=['status', 'cancelled_at', 'updated_at'])
            AuditLog.record(
                actor=request.user, action='REGISTRATION_CANCELLED',
                description=f'Registration #{registration.id} (event #{registration.event_id}) cancelled.',
            )
        return Response(RegistrationSerializer(registration, context=self.get_serializer_context()).data)

    @extend_schema(
        parameters=[
            OpenApiParameter('event', int, description='Restrict to one event.'),
            OpenApiParameter('student', int, description='Restrict to one student.'),
            OpenApiParameter('search', str, description='Matches username, full name or registration number.'),
            OpenApiParameter('registration_status', str, description='REGISTERED | CANCELLED.'),
            OpenApiParameter('participation_status', str, description='DRAFT | SUBMITTED.'),
            OpenApiParameter(
                'live_capture_status', str,
                description='NOT_SUBMITTED | AWAITING_EVENT | OPEN_TODAY | IN_PROGRESS | SUBMITTED.',
            ),
            OpenApiParameter('verification_status', str, description='The effective evidence decision.'),
            OpenApiParameter('certificate_status', str, description='The certificate position.'),
            OpenApiParameter('attendance_status', str, description='NOT_RECORDED | PENDING | APPROVED | REJECTED.'),
        ],
        responses={200: TrackingRowSerializer(many=True)},
    )
    @action(detail=False, methods=['get'], url_path='tracking')
    def tracking(self, request):
        """Where every registered student stands, across the whole workflow.

        Scoped exactly like the registration list itself, so an Event
        Coordinator or Faculty member sees their own department and a student
        sees only themselves. Narrowed to one student it is that student's
        chronological event history (requirement 10), which is why the
        ordering is by event date rather than by registration time.
        """
        queryset = tracking_queryset(self.get_queryset()).order_by('event__event_date', 'student__username')

        student_id = request.query_params.get('student')
        if student_id:
            if not str(student_id).isdigit():
                raise ValidationError({'student': 'Expected a numeric student id.'})
            queryset = queryset.filter(student_id=int(student_id))

        search = (request.query_params.get('search') or '').strip()
        if search:
            queryset = queryset.filter(
                Q(student__username__icontains=search)
                | Q(student__full_name__icontains=search)
                | Q(student__university_registration_number__icontains=search),
            )

        today = timezone.localdate()
        rows = [build_row(registration, today=today) for registration in queryset]
        # The derived statuses are computed, so they are filtered after the
        # database has already narrowed the set to one department.
        rows = apply_row_filters(rows, request.query_params)

        page = self.paginate_queryset(rows)
        if page is not None:
            return self.get_paginated_response(TrackingRowSerializer(page, many=True).data)
        return Response(TrackingRowSerializer(rows, many=True).data)
