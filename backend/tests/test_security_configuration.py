"""
Phase 9 §29/§31/§38 — security headers, environment-driven configuration,
media privacy and secret hygiene, asserted against the running configuration
and the repository itself.
"""

import pathlib
import re

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import AuthMixin, build_universe

REPO = pathlib.Path(__file__).resolve().parents[2]


class SecurityHeaderTests(AuthMixin, APITestCase):
    def setUp(self):
        self.u = build_universe()

    def test_every_response_carries_the_hardening_headers(self):
        self._auth_as('studenta')
        for name in ('user-me', 'event-list', 'dashboard'):
            response = self.client.get(reverse(name))
            self.assertEqual(response['X-Frame-Options'], 'DENY', name)
            self.assertEqual(response['X-Content-Type-Options'], 'nosniff', name)
            self.assertEqual(response['Referrer-Policy'], 'same-origin', name)
            self.assertEqual(response['Cross-Origin-Opener-Policy'], 'same-origin', name)

    def test_report_download_is_never_cacheable(self):
        self._auth_as('sysadmin')
        response = self.client.get(reverse('report-export', args=['system']), {'file_format': 'csv'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertRegex(response['Content-Disposition'], r'filename="[A-Za-z0-9._-]+"')

    def test_media_root_is_not_served_by_any_url(self):
        """Evidence images live under MEDIA_ROOT and must be reachable only
        through the authenticated capture-image view."""
        self._auth_as('sysadmin')
        stored_name = self.u.a.capture.object_reference.name
        for path in (f'/media/participation_captures/{stored_name}', f'/media/{stored_name}',
                     f'/{settings.MEDIA_URL}{stored_name}', f'/static/../media/{stored_name}'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, path)

    def test_evidence_image_is_never_cacheable(self):
        """An evidence image is private data streamed to an authorized viewer.
        Without an explicit directive a browser may keep it in its disk cache,
        where it stays readable on a shared machine after logout. The report
        download already sets no-store; this asserts the image does too."""
        self._auth_as('facultya')
        response = self.client.get(reverse('evidence-capture-image', args=[self.u.a.capture.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('no-store', response['Cache-Control'])

    def test_no_response_exposes_the_storage_path(self):
        self._auth_as('facultya')
        body = self.client.get(reverse('evidence-detail', args=[self.u.a.evidence.id])).content.decode()
        self.assertNotIn('participation_captures', body)
        self.assertNotIn(str(settings.MEDIA_ROOT), body)
        self.assertIn('/api/v1/evidence/captures/', body)  # the authenticated view, not the file

    def test_unhandled_paths_do_not_leak_debug_pages(self):
        response = self.client.get('/api/v1/does-not-exist/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn('Traceback', response.content.decode(errors='replace'))


class ConfigurationTests(SimpleTestCase):
    def test_settings_come_from_the_environment(self):
        source = (REPO / 'backend' / 'config' / 'settings.py').read_text(encoding='utf-8')
        for key in ('DJANGO_SECRET_KEY', 'DJANGO_DEBUG', 'DJANGO_ALLOWED_HOSTS', 'DATABASE_URL',
                    'CORS_ALLOWED_ORIGINS'):
            self.assertRegex(source, rf"config\(\s*'{key}'", key)
        self.assertNotIn('SECURE_BROWSER_XSS_FILTER', source)  # removed from Django in 4.0

    def test_cors_is_an_explicit_allowlist(self):
        self.assertFalse(getattr(settings, 'CORS_ORIGIN_ALLOW_ALL', False))
        self.assertTrue(all(origin.startswith('http') for origin in settings.CORS_ALLOWED_ORIGINS))
        self.assertNotIn('*', settings.CORS_ALLOWED_ORIGINS)

    def test_any_origin_is_confined_to_debug(self):
        # Development accepts any origin so the frontend can be served from
        # any port; production must not. Asserted against the source because
        # the test runner forces DEBUG off, which would make a runtime check
        # pass no matter how the setting were written.
        source = (REPO / 'backend' / 'config' / 'settings.py').read_text(encoding='utf-8')
        self.assertIn('CORS_ALLOW_ALL_ORIGINS = DEBUG', source)
        # ...and the production branch refuses to start if it is somehow on.
        block = source[source.index('if not DEBUG:'):]
        self.assertIn('CORS_ALLOW_ALL_ORIGINS', block)

    def test_production_branch_enables_https_hardening(self):
        source = (REPO / 'backend' / 'config' / 'settings.py').read_text(encoding='utf-8')
        block = source[source.index('if not DEBUG:'):]
        for key in ('SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'SECURE_HSTS_SECONDS'):
            self.assertIn(key, block, key)

    def test_jwt_rotation_and_blacklist_are_on(self):
        self.assertTrue(settings.SIMPLE_JWT['ROTATE_REFRESH_TOKENS'])
        self.assertTrue(settings.SIMPLE_JWT['BLACKLIST_AFTER_ROTATION'])
        self.assertIn('rest_framework_simplejwt.token_blacklist', settings.INSTALLED_APPS)
        self.assertLessEqual(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'].total_seconds(), 60 * 60)

    def test_default_permission_is_authenticated_and_throttling_is_on(self):
        rest = settings.REST_FRAMEWORK
        self.assertEqual(rest['DEFAULT_PERMISSION_CLASSES'], ('rest_framework.permissions.IsAuthenticated',))
        self.assertIn('rest_framework.throttling.ScopedRateThrottle', rest['DEFAULT_THROTTLE_CLASSES'])

    def test_media_is_private_storage(self):
        from apps.participation.storage import private_capture_storage
        # The storage is rooted under MEDIA_ROOT and MEDIA_URL is never routed
        # (test_media_root_is_not_served_by_any_url proves the 404), so no
        # stored key has a public URL. The storage location is the private root.
        self.assertTrue(str(private_capture_storage.location).startswith(str(settings.MEDIA_ROOT)))
        urls_source = (REPO / 'backend' / 'config' / 'urls.py').read_text(encoding='utf-8')
        self.assertNotIn('static(', urls_source)
        self.assertNotIn('MEDIA_URL', urls_source)


class SecretHygieneTests(SimpleTestCase):
    """The repository must not carry credentials. Values are never printed —
    a failure names the file and line only."""

    SUSPECT = re.compile(
        r'(postgres(ql)?://[^\s\'"]+:[^\s\'"]+@|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|'
        r'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,})',
    )
    SKIP_DIRS = {'node_modules', 'venv', 'dist', '.angular', '__pycache__', 'media', 'staticfiles', '.git'}
    EXTENSIONS = {'.py', '.ts', '.html', '.json', '.md', '.yaml', '.yml', '.example', '.txt', '.cfg', '.ini'}

    def _files(self):
        for path in REPO.rglob('*'):
            if any(part in self.SKIP_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix in self.EXTENSIONS:
                yield path

    def test_no_connection_strings_keys_or_tokens_in_source(self):
        offenders = []
        for path in self._files():
            try:
                text = path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if self.SUSPECT.search(line) and 'user:password@' not in line and 'ep-xxxx' not in line:
                    offenders.append(f'{path.relative_to(REPO)}:{number}')
        self.assertEqual(offenders, [], f'possible secrets at {offenders}')

    def test_env_files_are_ignored_and_example_has_placeholders_only(self):
        gitignore = (REPO / '.gitignore').read_text(encoding='utf-8')
        self.assertIn('.env', gitignore)
        self.assertIn('backend/.env', gitignore)
        example = (REPO / '.env.example').read_text(encoding='utf-8')
        self.assertIn('DJANGO_SECRET_KEY=change-me', example)
        self.assertRegex(example, re.compile(r'^DATABASE_URL=\s*$', re.M), 'DATABASE_URL in .env.example must be blank')
        # A Neon endpoint id is `ep-<two-words>-<hash>`; only the literal
        # `ep-xxxx` placeholder may appear in the example file.
        self.assertNotRegex(example, re.compile(r'ep-(?!xxxx)[a-z0-9-]+[^\s]*\.neon\.tech'))

    def test_real_env_file_is_not_tracked(self):
        import subprocess
        result = subprocess.run(['git', 'ls-files', '--error-unmatch', 'backend/.env'],
                                cwd=REPO, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0, 'backend/.env is tracked by git')
