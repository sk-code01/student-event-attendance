from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import ODRequest
from .permissions import CanAccessODRequest, CanRequestOD, CanReviewODRequest
from .serializers import ODRejectSerializer, ODRequestCreateSerializer, ODRequestSerializer


class ODRequestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    OD requests and their Event Coordinator decisions — an entirely separate resource from
    `/api/v1/attendance/`. Approving OD here never creates, changes or consults
    an attendance record, and an existing attendance record never blocks an OD
    request (or the reverse).

    As with attendance, there is no writable `status` and no update action:
    state changes only through `approve`/`reject`.
    """

    queryset = ODRequest.objects.select_related(
        'participation__student__department', 'participation__event', 'requested_by', 'reviewed_by',
    )
    serializer_class = ODRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return ODRequestCreateSerializer
        return ODRequestSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated(), CanRequestOD()]
        if self.action == 'retrieve':
            return [IsAuthenticated(), CanAccessODRequest()]
        if self.action in ('approve', 'reject'):
            return [IsAuthenticated(), CanReviewODRequest()]
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
            return queryset.filter(participation__event__department_id=user.department_id)
        if user.role == user.Role.STUDENT:
            return queryset.filter(participation__student=user)
        return queryset.none()

    @extend_schema(request=ODRequestCreateSerializer, responses={201: ODRequestSerializer})
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        od_request = services.request_od(
            participation=serializer.validated_data['participation'],
            requested_by=request.user,
            reason=serializer.validated_data['reason'],
        )
        return Response(
            ODRequestSerializer(od_request, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=None, responses=ODRequestSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        od_request = self.get_object()
        od_request = services.approve_od(od_request=od_request, reviewer=request.user)
        return Response(ODRequestSerializer(od_request, context=self.get_serializer_context()).data)

    @extend_schema(request=ODRejectSerializer, responses=ODRequestSerializer)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        od_request = self.get_object()
        serializer = ODRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        od_request = services.reject_od(
            od_request=od_request, reviewer=request.user, reason=serializer.validated_data['reason'],
        )
        return Response(ODRequestSerializer(od_request, context=self.get_serializer_context()).data)
