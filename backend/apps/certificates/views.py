from django.http import FileResponse, Http404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.participation.models import Participation

from . import services
from .models import MAX_CERTIFICATE_ATTEMPTS, Certificate
from .permissions import (
    CanAcceptExhaustedCertificate,
    CanAccessCertificate,
    CanVerifyCertificate,
)
from .serializers import (
    CertificateDecisionSerializer,
    CertificateFinalDecisionSerializer,
    CertificateEligibilitySerializer,
    CertificateSerializer,
    CertificateUploadSerializer,
)


class CertificateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Certificates, scoped by role.

    The queryset is the security boundary: a student sees only their own, a
    Faculty member or Event Coordinator only their department's, and Admin
    sees everything. Anything outside that is a 404, never a 403, so an id
    that exists but is not yours is indistinguishable from one that does not.
    """

    serializer_class = CertificateSerializer
    permission_classes = [IsAuthenticated]
    queryset = Certificate.objects.none()  # real scoping is in get_queryset; declared for schema generation

    def get_queryset(self):
        user = self.request.user
        queryset = Certificate.objects.select_related(
            'participation__student__department', 'participation__event', 'reviewed_by',
        ).prefetch_related('participation__certificates')

        if user.is_superuser or user.role == user.Role.ADMIN:
            return queryset
        if user.role in (user.Role.FACULTY, user.Role.EVENT_COORDINATOR):
            return queryset.filter(participation__event__department_id=user.department_id)
        return queryset.filter(participation__student_id=user.id)

    def get_permissions(self):
        if self.action == 'decide':
            return [IsAuthenticated(), CanVerifyCertificate()]
        if self.action in ('accept', 'final_decision'):
            return [IsAuthenticated(), CanAcceptExhaustedCertificate()]
        if self.action == 'retrieve':
            return [IsAuthenticated(), CanAccessCertificate()]
        return [IsAuthenticated()]

    @extend_schema(request=CertificateUploadSerializer, responses={201: CertificateSerializer})
    @action(detail=False, methods=['post'], url_path='upload')
    def upload(self, request):
        """Student submits a certificate attempt."""
        serializer = CertificateUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Resolved through the student's own participations, so one student can
        # never submit against another's participation id.
        try:
            participation = Participation.objects.select_related('event', 'student').get(
                pk=serializer.validated_data['participation'], student_id=request.user.id,
            )
        except Participation.DoesNotExist:
            raise Http404

        certificate = services.submit_certificate(
            participation=participation,
            user=request.user,
            uploaded_file=serializer.validated_data['file'],
        )
        return Response(
            CertificateSerializer(certificate, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(responses={200: CertificateEligibilitySerializer})
    @action(detail=False, methods=['get'], url_path='eligibility')
    def eligibility(self, request):
        """Whether the student may upload for a participation right now."""
        participation_id = request.query_params.get('participation')
        if not participation_id:
            return Response({'detail': 'participation is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            participation = Participation.objects.select_related('event').prefetch_related(
                'certificates',
            ).get(pk=participation_id, student_id=request.user.id)
        except (Participation.DoesNotExist, ValueError):
            raise Http404

        reason = services.certificate_window_closed_reason(participation)
        payload = {
            'can_upload': reason is None,
            'reason': reason,
            'window_opens_on': services.certificate_window_opens_on(participation.event),
            'attempts_used': services.attempts_used(participation),
            'attempts_remaining': services.attempts_remaining(participation),
            'max_attempts': MAX_CERTIFICATE_ATTEMPTS,
        }
        return Response(CertificateEligibilitySerializer(payload).data)

    @extend_schema(request=CertificateDecisionSerializer, responses={200: CertificateSerializer})
    @action(detail=True, methods=['post'], url_path='decision')
    def decide(self, request, pk=None):
        """Faculty verifies or rejects a certificate."""
        certificate = self.get_object()
        serializer = CertificateDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        certificate = services.record_faculty_decision(
            certificate=certificate,
            reviewer=request.user,
            decision=serializer.validated_data['decision'],
            reason=serializer.validated_data.get('reason', ''),
        )
        return Response(CertificateSerializer(certificate, context={'request': request}).data)

    @extend_schema(request=None, responses={200: CertificateSerializer})
    @action(detail=True, methods=['post'], url_path='accept')
    def accept(self, request, pk=None):
        """Event Coordinator accepts a rejected certificate after the student's
        attempts are exhausted."""
        certificate = self.get_object()
        certificate = services.accept_exhausted_certificate(
            certificate=certificate, coordinator=request.user,
        )
        return Response(CertificateSerializer(certificate, context={'request': request}).data)

    @extend_schema(request=CertificateFinalDecisionSerializer, responses={200: CertificateSerializer})
    @action(detail=True, methods=['post'], url_path='final-decision')
    def final_decision(self, request, pk=None):
        """Event Coordinator's final accept/reject after Faculty verification.

        Requirement 23 places the coordinator after verification rather than
        instead of it, so only a certificate Faculty have already verified can
        reach this. A rejection here opens no new resubmission path.
        """
        certificate = self.get_object()
        serializer = CertificateFinalDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        certificate = services.record_final_decision(
            certificate=certificate,
            coordinator=request.user,
            decision=serializer.validated_data['decision'],
            reason=serializer.validated_data.get('reason', ''),
        )
        return Response(CertificateSerializer(certificate, context={'request': request}).data)


class CertificateFileView(APIView):
    """Streams a certificate's bytes.

    This is the only way any client reads a certificate back — the storage
    path and URL are never exposed — and it applies the same object-level
    authorization as the record itself.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: {'type': 'string', 'format': 'binary'}})
    def get(self, request, pk):
        try:
            certificate = Certificate.objects.select_related(
                'participation__event', 'participation__student',
            ).get(pk=pk)
        except Certificate.DoesNotExist:
            raise Http404

        if not CanAccessCertificate().has_object_permission(request, self, certificate):
            raise Http404

        response = FileResponse(
            certificate.object_reference.open('rb'), content_type=certificate.mime_type,
        )
        # A certificate is a personal document: nothing between the authorized
        # viewer and this process may retain a copy, which is the same rule the
        # evidence image and report download paths already apply.
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response['Content-Disposition'] = (
            f'attachment; filename="certificate-{certificate.id}.'
            f'{certificate.mime_type.rsplit("/", 1)[-1]}"'
        )
        return response
