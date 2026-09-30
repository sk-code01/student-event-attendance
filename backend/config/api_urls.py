"""
Root of the /api/v1/ namespace. Each app mounts its own urls.py here as it
is implemented in later phases.
"""

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from .views import health_check, readiness_check

urlpatterns = [
    # Liveness (always 200 while the process serves) and readiness
    # (503 when the database is unreachable) — see config/views.py.
    path('health/', health_check, name='health-check'),
    path('health/ready/', readiness_check, name='readiness-check'),

    # Authentication (JWT) and user/role management
    path('auth/', include('apps.accounts.auth_urls')),
    path('users/', include('apps.accounts.user_urls')),
    path('departments/', include('apps.departments.urls')),

    # Event management and registration
    path('colleges/', include('apps.colleges.urls')),
    path('events/', include('apps.events.urls')),
    path('registrations/', include('apps.registrations.urls')),

    # Live participation capture
    path('participations/', include('apps.participation.urls')),

    # Evidence versioning + faculty verification + Event Coordinator override
    path('evidence/', include('apps.verification.urls')),

    # Certificates: student upload, Faculty verification, Event Coordinator
    # acceptance once the student's attempts are exhausted
    path('certificates/', include('apps.certificates.urls')),

    # Attendance, OD and achievements (independent post-verification workflows)
    path('attendance/', include('apps.attendance.urls')),
    path('od/', include('apps.od.urls')),
    path('achievements/', include('apps.achievements.urls')),

    # Notifications, dashboards, activity and the audit trail
    path('notifications/', include('apps.notifications.urls')),
    path('dashboard/', include('apps.dashboard.urls')),
    path('activity/', include('apps.audit.activity_urls')),
    path('audit/', include('apps.audit.urls')),

    # Analytics and reporting
    path('analytics/', include('apps.analytics.urls')),
    path('reports/', include('apps.reports.urls')),

    # AI decision support (Phase 8): recommendations, risk signals, engagement clusters
    path('recommendations/', include('apps.ai.urls_recommendations')),
    path('anomalies/', include('apps.ai.urls_anomalies')),
    path('engagement/', include('apps.ai.urls_engagement')),

    # OpenAPI / Swagger documentation
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
