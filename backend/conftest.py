import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    """DRF's rate throttles (including the 'auth' scope on login/register)
    are backed by Django's process-wide cache, which persists across test
    cases in the same run. Without clearing it, tests that call these
    endpoints repeatedly start tripping 429s unrelated to what they're
    actually testing."""
    cache.clear()
    yield
