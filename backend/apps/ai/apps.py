from django.apps import AppConfig


class AiConfig(AppConfig):
    """No models: the AI layer derives every feature from the authoritative
    operational tables at request time and stores nothing of its own."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ai'
    label = 'ai'
