"""
Operational probes. Deliberately tiny and deliberately uninformative about
internals: they say whether the service is up and whether its one external
dependency (the database) answers, and nothing else. No settings values, no
credentials, no connection strings, no stack traces.
"""

import logging

from django.db import connection
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def _database_reachable() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        return True
    except Exception:
        # The exception text can name the host and user of the connection
        # string, so it is logged server-side at warning level and never
        # returned to the caller.
        logger.warning('Health probe: database connectivity check failed.', exc_info=True)
        return False


@extend_schema(
    responses={200: OpenApiResponse(description='Service is reachable and reports its status.')},
)
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Liveness probe.

    Always answers 200 while the process is able to serve a request, and
    reports database reachability as a field rather than as the status code.
    A load balancer that restarts on a failed liveness probe must use this
    one: a transient database blip should not cause the app to be killed.
    """
    return Response({
        'status': 'ok',
        'service': 'smart-student-event-attendance-api',
        'version': 'v1',
        'database': 'ok' if _database_reachable() else 'unavailable',
        'server_time': timezone.now(),
    })


@extend_schema(
    responses={
        200: OpenApiResponse(description='Application and database are both ready to serve traffic.'),
        503: OpenApiResponse(description='A dependency is not ready; do not route traffic here yet.'),
    },
)
@api_view(['GET'])
@permission_classes([AllowAny])
def readiness_check(request):
    """Readiness probe.

    Unlike the liveness probe this one *fails* (503) when the database is
    unreachable, so a reverse proxy or orchestrator can stop sending traffic
    to an instance that cannot serve it — for example during a rolling
    deploy, before migrations have finished.
    """
    ready = _database_reachable()
    return Response(
        {
            'status': 'ready' if ready else 'not-ready',
            'checks': {'database': 'ok' if ready else 'unavailable'},
            'server_time': timezone.now(),
        },
        status=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
