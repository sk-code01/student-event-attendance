from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import Attendance
from .permissions import (
    CanAccessAttendance,
    CanMarkAttendance,
    CanRequestAttendance,
    CanReviewAttendance,
)
from .serializers import (
    AttendanceMarkSerializer,
    AttendanceRejectSerializer,
    AttendanceRequestSerializer,
    AttendanceSerializer,
)


class AttendanceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Attendance requests and their Event Coordinator decisions.

    There is no `update`/`partial_update` and no writable `status` anywhere:
    the only ways a record changes state are the `approve` and `reject` detail
    actions, which derive everything (new status, reviewer, review timestamp)
    from the authenticated user and the current state. That is what makes
    client-side status/reviewer/timestamp spoofing structurally impossible
    rather than merely validated against.
    """

    queryset = Attendance.objects.select_related(
        'participation__student__department', 'participation__event',
        'registration__student__department', 'registration__event', 'requested_by', 'reviewed_by',
    )
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return AttendanceRequestSerializer
        return AttendanceSerializer

    def get_permissions(self):
        if getattr(self, 'action', None) == 'mark':
            return [IsAuthenticated(), CanMarkAttendance()]
        if self.action == 'create':
            return [IsAuthenticated(), CanRequestAttendance()]
        if self.action == 'retrieve':
            return [IsAuthenticated(), CanAccessAttendance()]
        if self.action in ('approve', 'reject'):
            return [IsAuthenticated(), CanReviewAttendance()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()
        if user.is_superuser or user.role == user.Role.ADMIN:
            return queryset
        if user.role in (user.Role.FACULTY, user.Role.EVENT_COORDINATOR):
            # A staff user with no department sees nothing, rather than
            # implicitly matching every department-less event via NULL = NULL.
            if user.department_id is None:
                return queryset.none()
            return queryset.filter(registration__event__department_id=user.department_id)
        if user.role == user.Role.STUDENT:
            return queryset.filter(registration__student=user)
        return queryset.none()

    @extend_schema(request=AttendanceRequestSerializer, responses={201: AttendanceSerializer})
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attendance = services.request_attendance(
            participation=serializer.validated_data['participation'], requested_by=request.user,
        )
        return Response(
            AttendanceSerializer(attendance, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=None, responses=AttendanceSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        attendance = self.get_object()
        attendance = services.approve_attendance(attendance=attendance, reviewer=request.user)
        return Response(AttendanceSerializer(attendance, context=self.get_serializer_context()).data)

    @extend_schema(request=AttendanceRejectSerializer, responses=AttendanceSerializer)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        attendance = self.get_object()
        serializer = AttendanceRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attendance = services.reject_attendance(
            attendance=attendance, reviewer=request.user, reason=serializer.validated_data['reason'],
        )
        return Response(AttendanceSerializer(attendance, context=self.get_serializer_context()).data)

    @extend_schema(request=AttendanceMarkSerializer, responses={200: AttendanceSerializer})
    @action(detail=False, methods=['post'], url_path='mark')
    def mark(self, request):
        """Event Coordinator records or updates attendance directly.

        Unlike the Faculty request path this does not require verified
        evidence: a student who never submitted a live capture has nothing to
        verify, and recording their attendance is exactly what this is for.
        """
        serializer = AttendanceMarkSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)

        attendance = services.mark_attendance(
            registration=serializer.validated_data['registration'],
            coordinator=request.user,
            status=serializer.validated_data['status'],
            reason=serializer.validated_data.get('reason', ''),
        )
        return Response(AttendanceSerializer(attendance, context={'request': request}).data)
