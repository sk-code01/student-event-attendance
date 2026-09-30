"""
Report endpoints.

`GET /api/v1/reports/`                      — report types this caller may run
`GET /api/v1/reports/{type}/`               — a JSON preview of the dataset
`GET /api/v1/reports/{type}/export/?file_format=` — the generated file

Security shape:
  * report type and format come from closed allowlists, never from raw input;
  * the dataset is built from `AnalyticsScope`, so rows are scoped to the
    caller before the file is rendered;
  * rendering happens in memory and the bytes are streamed back over the
    authenticated request — no file is written, and no report is ever exposed
    at a public URL;
  * every request re-checks authorization; the UI listing is convenience only.
"""

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.filters import AnalyticsFilters
from apps.analytics.scope import AnalyticsScope
from apps.audit.models import AuditLog

from . import datasets, renderers, registry
from .serializers import ReportDatasetSerializer, ReportTypeSerializer

_FILTER_PARAMS = [
    OpenApiParameter('date_from', str, description='Inclusive ISO date (YYYY-MM-DD).'),
    OpenApiParameter('date_to', str, description='Inclusive ISO date (YYYY-MM-DD).'),
    OpenApiParameter('event', int, description='Restrict to one event within your scope.'),
    OpenApiParameter('category', str, description='Restrict to one event category.'),
    OpenApiParameter('department', int, description='Admin only may name another department.'),
    OpenApiParameter('student', int, description='Staff only, within their own scope.'),
]


def _resolve(report_type, user):
    """Allowlist lookup plus the role check.

    An unknown type is a 404 and a forbidden one is a 403 — the type names are
    a fixed public vocabulary, so distinguishing them leaks nothing.
    """
    definition = registry.get_definition(report_type)
    if definition is None:
        raise NotFound('Unknown report type.')
    if not definition.allows(user):
        raise PermissionDenied('This report type is not available for your role.')
    return definition


@extend_schema(responses=ReportTypeSerializer(many=True), tags=['reports'])
class ReportTypeListView(APIView):
    """The report types this caller may run. Convenience for the UI; the export
    endpoint re-checks independently."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        available = registry.available_for(request.user)
        payload = [
            {
                'key': d.key,
                'title': d.title,
                'description': d.description,
                'formats': list(registry.FORMATS),
            }
            for d in available
        ]
        return Response(ReportTypeSerializer(payload, many=True).data)


@extend_schema(parameters=_FILTER_PARAMS, responses=ReportDatasetSerializer, tags=['reports'])
class ReportPreviewView(APIView):
    """A JSON view of exactly the rows the exported file will contain, so the
    UI can preview without downloading. Same scope, same builder."""

    permission_classes = [IsAuthenticated]

    def get(self, request, report_type):
        definition = _resolve(report_type, request.user)
        filters = AnalyticsFilters.from_request(request)
        scope = AnalyticsScope(user=request.user, filters=filters)
        dataset = datasets.build(definition, scope)
        return Response(ReportDatasetSerializer({
            'key': definition.key,
            'title': dataset.title,
            'description': dataset.description,
            'columns': dataset.columns,
            'rows': [[('' if v is None else str(v)) for v in row] for row in dataset.rows],
            'row_count': len(dataset.rows),
            'filters': filters.summary(),
        }).data)


@extend_schema(
    parameters=_FILTER_PARAMS + [
        OpenApiParameter(
            'file_format', str,
            description=f'One of: {", ".join(registry.FORMATS)}. Defaults to csv. '
                        'Named file_format because DRF reserves "format" for renderer '
                        'content negotiation.',
        ),
    ],
    responses={200: {'type': 'string', 'format': 'binary'}},
    tags=['reports'],
)
class ReportExportView(APIView):
    """Generates and streams the file."""

    permission_classes = [IsAuthenticated]
    throttle_scope = 'reports'

    def get(self, request, report_type):
        definition = _resolve(report_type, request.user)

        # Deliberately NOT called `format`: DRF reserves that query parameter
        # for renderer content negotiation (URL_FORMAT_OVERRIDE), so
        # `?format=csv` makes APIView.initial() raise Http404 before
        # authentication ever runs. Renaming keeps the collision local instead
        # of disabling `?format=json` on every other endpoint in the project.
        # An absent or empty value means "unspecified" and defaults to CSV —
        # `?file_format=` is indistinguishable from omitting it in a query
        # string, and many clients always send the key. The default is itself
        # allowlisted, so this can never yield an unsafe format. Any *non-empty*
        # value must be in the allowlist.
        fmt = (request.query_params.get('file_format') or registry.CSV).strip().lower()
        if fmt not in registry.FORMATS:
            raise ValidationError(
                {'file_format': f'Unsupported format. Choose one of: {", ".join(registry.FORMATS)}.'},
            )

        filters = AnalyticsFilters.from_request(request)
        scope = AnalyticsScope(user=request.user, filters=filters)
        dataset = datasets.build(definition, scope)

        content = renderers.render(
            dataset, fmt=fmt, user=request.user, filter_summary=filters.summary(),
        )
        filename = renderers.build_filename(definition, fmt)

        # Audited as a business action: who generated what, in which format,
        # over which filters. Never the report contents, and never a token.
        AuditLog.record(
            actor=request.user, action='REPORT_GENERATED',
            description=(
                f'{definition.title} exported as {fmt.upper()} '
                f'({len(dataset.rows)} rows; filters: {filters.summary()}).'
            ),
        )

        response = HttpResponse(content, content_type=renderers.CONTENT_TYPES[fmt])
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Content-Length'] = str(len(content))
        # Personal/academic data: never cached by a proxy or the browser.
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        return response
