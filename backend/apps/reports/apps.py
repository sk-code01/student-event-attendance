from django.apps import AppConfig


class ReportsConfig(AppConfig):
    """No models: reports are generated on demand from the same scoped
    querysets analytics uses, streamed to the caller, and never written to a
    publicly reachable location."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.reports'
    label = 'reports'
