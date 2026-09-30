from django.apps import AppConfig


class DashboardConfig(AppConfig):
    """No models: the dashboard is a read-only aggregation layer over the
    other apps, so this app exists only to host its service, serializers,
    views and urls."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.dashboard'
    label = 'dashboard'
