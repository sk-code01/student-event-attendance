from django.http import FileResponse, Http404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsStudent

from . import services
from .models import Evidence, EvidenceCapture, EvidenceVerification, EvidenceVersion
from .permissions import CanAccessEvidence, CanOverrideVerification, CanVerifyEvidence
from .serializers import (
    DecisionSerializer,
    EvidenceCaptureCreateSerializer,
    EvidenceCaptureSerializer,
    EvidenceOpenSerializer,
    EvidenceSerializer,
    EvidenceVersionSerializer,
    OverrideSerializer,
)


class EvidenceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    `POST /api/v1/evidence/` opens (or idempotently re-fetches) the current
    evidence version for the caller's own participation — the student-side
    entry point into the workflow, replacing what used to be the
    "add capture directly to a participation" step in Phase 3. Faculty/Event Coordinator
    decision actions live here as detail actions rather than under a
    separate `/verification/` resource, since the full decision history is
    already nested on the evidence detail response and a parallel resource
    would just duplicate it.
    """

    # The read serializer walks versions -> captures/verifications -> reviewer and
    # the student's department for every row; without these the list issues
    # ~8 queries per evidence record (found by the Phase 9 query-budget test).
    queryset = Evidence.objects.select_related(
        'participation__student__department', 'participation__event__conducting_college', 'current_version',
    ).prefetch_related('versions__captures', 'versions__verifications__reviewer')
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return EvidenceOpenSerializer
        return EvidenceSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated(), IsStudent()]
        if self.action == 'retrieve':
            return [IsAuthenticated(), CanAccessEvidence()]
        if self.action in ('verify', 'reject', 'request_resubmission'):
            return [IsAuthenticated(), CanVerifyEvidence()]
        if self.action == 'override':
            return [IsAuthenticated(), CanOverrideVerification()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()
        if user.is_superuser or user.role == user.Role.ADMIN:
            return queryset
        if user.role in (user.Role.FACULTY, user.Role.EVENT_COORDINATOR):
            return queryset.filter(participation__event__department_id=user.department_id)
        if user.role == user.Role.STUDENT:
            return queryset.filter(participation__student=user)
        return queryset.none()

    def retrieve(self, request, *args, **kwargs):
        evidence = self.get_object()
        if request.user.role == request.user.Role.FACULTY:
            services.mark_under_review(evidence=evidence, viewer=request.user)
            evidence.refresh_from_db()
        return Response(self.get_serializer(evidence).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = services.open_evidence_version(
            participation=serializer.validated_data['participation'], user=request.user,
        )
        return Response(
            EvidenceSerializer(version.evidence, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=DecisionSerializer, responses=EvidenceSerializer)
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        return self._decide(request, EvidenceVerification.Decision.VERIFIED)

    @extend_schema(request=DecisionSerializer, responses=EvidenceSerializer)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        return self._decide(request, EvidenceVerification.Decision.REJECTED)

    @extend_schema(request=DecisionSerializer, responses=EvidenceSerializer)
    @action(detail=True, methods=['post'], url_path='request-resubmission')
    def request_resubmission(self, request, pk=None):
        return self._decide(request, EvidenceVerification.Decision.RESUBMISSION_REQUIRED)

    def _decide(self, request, decision):
        evidence = self.get_object()
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.record_faculty_decision(
            evidence=evidence, reviewer=request.user, decision=decision, reason=serializer.validated_data['reason'],
        )
        evidence.refresh_from_db()
        return Response(EvidenceSerializer(evidence, context=self.get_serializer_context()).data)

    @extend_schema(request=OverrideSerializer, responses=EvidenceSerializer)
    @action(detail=True, methods=['post'])
    def override(self, request, pk=None):
        evidence = self.get_object()
        serializer = OverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.record_event_coordinator_override(
            evidence=evidence, event_coordinator=request.user,
            decision=serializer.validated_data['decision'], reason=serializer.validated_data['reason'],
        )
        evidence.refresh_from_db()
        return Response(EvidenceSerializer(evidence, context=self.get_serializer_context()).data)


def _get_visible_version_or_404(request, version_id) -> EvidenceVersion:
    try:
        version = EvidenceVersion.objects.select_related(
            'evidence__participation__student', 'evidence__participation__event',
        ).get(pk=version_id)
    except EvidenceVersion.DoesNotExist:
        raise Http404
    if not CanAccessEvidence().has_object_permission(request, None, version.evidence):
        raise Http404
    return version


class EvidenceVersionCaptureUploadView(APIView):
    """Uploads one capture to an in-progress evidence version, reusing the
    exact same server-side validation pipeline
    (apps.participation.validation) as Phase 3."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=EvidenceCaptureCreateSerializer, responses=EvidenceCaptureSerializer)
    def post(self, request, version_id):
        version = _get_visible_version_or_404(request, version_id)
        if not (request.user.role == request.user.Role.STUDENT
                and version.evidence.participation.student_id == request.user.id):
            raise PermissionDenied('Only the participating student may upload a capture.')

        serializer = EvidenceCaptureCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        capture = services.add_capture_to_version(version=version, user=request.user, **serializer.validated_data)
        return Response(
            EvidenceCaptureSerializer(capture, context={'request': request}).data, status=status.HTTP_201_CREATED,
        )


class EvidenceVersionSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=EvidenceVersionSerializer)
    def post(self, request, version_id):
        version = _get_visible_version_or_404(request, version_id)
        if not (request.user.role == request.user.Role.STUDENT
                and version.evidence.participation.student_id == request.user.id):
            raise PermissionDenied('Only the participating student may submit this evidence version.')

        version = services.submit_version(version=version, user=request.user)
        return Response(EvidenceVersionSerializer(version, context={'request': request}).data)


class EvidenceCaptureImageView(APIView):
    """Streams a capture's image bytes. This — not the storage path/URL —
    is the only way any client ever reads a capture image back, gated by
    the same object-level authorization as the parent evidence record."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: {'type': 'string', 'format': 'binary'}})
    def get(self, request, pk):
        try:
            capture = EvidenceCapture.objects.select_related(
                'evidence_version__evidence__participation__event',
            ).get(pk=pk)
        except EvidenceCapture.DoesNotExist:
            raise Http404

        # Outside the caller's scope resolves to 404, exactly like every other
        # resource in this project: an existing-but-forbidden capture id must
        # not be distinguishable from a nonexistent one.
        if not CanAccessEvidence().has_object_permission(request, self, capture.evidence_version.evidence):
            raise Http404

        response = FileResponse(capture.object_reference.open('rb'), content_type=capture.mime_type)
        # Private evidence must not be retained by anything between the
        # authorized viewer and this process. Without an explicit directive a
        # browser is free to keep the image in its disk cache, which would
        # leave it readable on a shared machine after logout. The report
        # download path already sets exactly this; an evidence image is at
        # least as sensitive.
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        return response
