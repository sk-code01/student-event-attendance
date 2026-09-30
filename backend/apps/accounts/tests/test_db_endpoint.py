"""Proves the endpoint swap fires under `manage.py test` and not otherwise."""
from django.conf import settings
from django.test import SimpleTestCase


class TestEndpointTests(SimpleTestCase):
    def test_tests_run_against_the_direct_endpoint_not_the_pooler(self):
        host = settings.DATABASES['default']['HOST']
        self.assertNotIn('-pooler.', host, f'test run is still pooled: {host}')

    def test_tests_do_not_hold_persistent_connections(self):
        # A persistent connection to the template database is enough to make
        # `CREATE DATABASE ... TEMPLATE` fail for every parallel worker.
        self.assertEqual(settings.DATABASES['default']['CONN_MAX_AGE'], 0)
