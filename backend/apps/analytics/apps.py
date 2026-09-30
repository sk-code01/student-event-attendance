from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    """No models: analytics is a read-only aggregation layer over the existing
    operational data. There is no analytics database and no second source of
    truth."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.analytics'
    label = 'analytics'
