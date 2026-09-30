from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import Achievement
from .permissions import (
    CanAccessAchievement,
    CanCreateAchievement,
    CanEditAchievement,
    CanReviewAchievement,
)
from .serializers import (
    AchievementCreateSerializer,
    AchievementRejectSerializer,
    AchievementSerializer,
    AchievementUpdateSerializer,
)


class AchievementViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Achievement records.

    `partial_update` exists (the draft-editing path) but cannot change status:
    the writable serializer carries only the descriptive fields, and the
    service layer additionally refuses anything that is not still a DRAFT
    belonging to the caller. Status only ever moves through the dedicated
    `submit`, `approve` and `reject` actions.
    """

    queryset = Achievement.objects.select_related(
        'participation__student__department', 'participation__event', 'created_by', 'reviewed_by',
    )
    serializer_class = AchievementSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_serializer_class(self):
        if self.action == 'create':
            return AchievementCreateSerializer
        if self.action == 'partial_update':
            return AchievementUpdateSerializer
        return AchievementSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated(), CanCreateAchievement()]
        if self.action == 'retrieve':
            return [IsAuthenticated(), CanAccessAchievement()]
        if self.action in ('partial_update', 'submit'):
            return [IsAuthenticated(), CanEditAchievement()]
        if self.action in ('approve', 'reject'):
            return [IsAuthenticated(), CanReviewAchievement()]
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
            # A student sees every record about themselves — approved ones as
            # official achievements, pending/rejected ones clearly labelled by
            # `status` so the UI can distinguish them. They never see another
            # student's records, and never see one they could mistake for
            # official (`is_official` is true only for APPROVED).
            return queryset.filter(participation__student=user)
        return queryset.none()

    @extend_schema(request=AchievementCreateSerializer, responses={201: AchievementSerializer})
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        achievement = services.create_achievement(
            participation=data.pop('participation'),
            creator=request.user,
            submit_for_approval=data.pop('submit_for_approval'),
            **data,
        )
        return Response(
            AchievementSerializer(achievement, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=AchievementUpdateSerializer, responses=AchievementSerializer)
    def partial_update(self, request, *args, **kwargs):
        achievement = self.get_object()
        serializer = AchievementUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        achievement = services.update_achievement(
            achievement=achievement, user=request.user, **serializer.validated_data,
        )
        return Response(AchievementSerializer(achievement, context=self.get_serializer_context()).data)

    @extend_schema(request=None, responses=AchievementSerializer)
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        achievement = self.get_object()
        achievement = services.submit_achievement(achievement=achievement, user=request.user)
        return Response(AchievementSerializer(achievement, context=self.get_serializer_context()).data)

    @extend_schema(request=None, responses=AchievementSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        achievement = self.get_object()
        achievement = services.approve_achievement(achievement=achievement, reviewer=request.user)
        return Response(AchievementSerializer(achievement, context=self.get_serializer_context()).data)

    @extend_schema(request=AchievementRejectSerializer, responses=AchievementSerializer)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        achievement = self.get_object()
        serializer = AchievementRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        achievement = services.reject_achievement(
            achievement=achievement, reviewer=request.user, reason=serializer.validated_data['reason'],
        )
        return Response(AchievementSerializer(achievement, context=self.get_serializer_context()).data)
