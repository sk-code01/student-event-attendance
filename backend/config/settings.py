"""
Django settings for the Smart Student Event Participation and Attendance
Management System.
"""

import sys
from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Core / security
# ---------------------------------------------------------------------------

# DEBUG is read first: it decides which of the settings below are allowed to
# fall back to a development-only default and which must be supplied by the
# environment. Anything that would be a security defect in production fails
# loudly at import time rather than silently starting up misconfigured.
DEBUG = config('DJANGO_DEBUG', default=True, cast=bool)

DEV_SECRET_KEY = 'django-insecure-dev-key-change-me'
SECRET_KEY = config('DJANGO_SECRET_KEY', default=DEV_SECRET_KEY)
if not DEBUG and SECRET_KEY in ('', DEV_SECRET_KEY):
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY must be set to a real, random secret when DJANGO_DEBUG=False. '
        'The development fallback key is never usable in production.'
    )

ALLOWED_HOSTS = config('DJANGO_ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())
if not DEBUG:
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS must list the deployment hostnames when DJANGO_DEBUG=False.')
    if '*' in ALLOWED_HOSTS:
        raise ImproperlyConfigured('DJANGO_ALLOWED_HOSTS must not contain a wildcard when DJANGO_DEBUG=False.')

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_spectacular',
    'django_filters',
    # Local apps
    'apps.accounts',
    'apps.departments',
    'apps.colleges',
    'apps.events',
    'apps.registrations',
    'apps.audit',
    'apps.participation',
    'apps.verification',
    'apps.certificates',
    'apps.attendance',
    'apps.od',
    'apps.achievements',
    'apps.notifications',
    'apps.dashboard',
    'apps.analytics',
    'apps.reports',
    'apps.ai',
]

AUTH_USER_MODEL = 'accounts.User'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'config.middleware.RejectNullBytesMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

if not DEBUG:
    # WhiteNoise serves Django's own static files (admin, DRF browsable API,
    # Swagger UI) straight from the WSGI process, so a production deployment
    # needs no static-file rule in the reverse proxy. It never touches
    # MEDIA_ROOT — evidence images are not static files and are not served
    # by any middleware.
    #
    # Only installed outside DEBUG: `runserver` already serves static files
    # itself, and WhiteNoise would otherwise warn on every request about the
    # `staticfiles/` directory that only exists after `collectstatic`.
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ---------------------------------------------------------------------------
# Database. PostgreSQL (NeonDB) is the one and only supported database, in
# development as well as in production, addressed by a single DATABASE_URL
# connection string exactly as Neon's dashboard provides it:
#
#   postgresql://user:password@ep-xxxx.<region>.aws.neon.tech/dbname?sslmode=require
#
# There is deliberately no SQLite fallback. A missing DATABASE_URL is a
# configuration error, not a cue to quietly start against a different
# database engine: doing so would let migrations, constraints and query
# behaviour diverge from what actually runs in production.
#
# `ssl_require=True` is unconditional — Neon only accepts TLS connections,
# and it also stops a copy-pasted URL that dropped `?sslmode=require` from
# downgrading the connection. `conn_max_age` keeps connections alive between
# requests; keep it modest, because Neon's pooler counts idle sessions.
# ---------------------------------------------------------------------------

DATABASE_URL = config('DATABASE_URL', default='')

if not DATABASE_URL:
    raise ImproperlyConfigured(
        'DATABASE_URL is required. Copy .env.example to backend/.env and set it to the '
        'NeonDB PostgreSQL connection string from your Neon project dashboard. This project '
        'has no SQLite fallback by design.'
    )

DATABASES = {
    'default': dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=config('DB_CONN_MAX_AGE', default=60, cast=int),
        ssl_require=True,
    )
}

# ---------------------------------------------------------------------------
# Test runs bypass the connection pooler.
#
# Neon offers two endpoints for the same database: a direct one, and a pooled
# one whose host carries a `-pooler` suffix. The pooled endpoint is the right
# default for serving requests, which is why DATABASE_URL names it.
#
# It is the wrong endpoint for `manage.py test`. The parallel test runner
# creates `test_<name>` and then clones it once per worker with
# `CREATE DATABASE ... TEMPLATE test_<name>`, and PostgreSQL refuses that while
# any session is connected to the template. A pooler holds server-side sessions
# open after the client disconnects — that is what pooling *is* — so the clone
# failed every time with "source database is being accessed by other users",
# on a database nothing was actually using.
#
# Switching to the direct endpoint for tests fixes it at the cause. CONN_MAX_AGE
# goes to 0 for the same reason: persistent connections would leave the runner
# holding the template itself.
#
# This is deliberately keyed off `sys.argv` rather than off DEBUG or an
# environment variable, so it cannot drift out of step with how the suite is
# actually invoked, and so it can never alter a running server.
# ---------------------------------------------------------------------------

# `manage.py test ...` puts the literal 'test' in argv. pytest does not — under
# `python -m pytest` argv[0] is its own __main__.py — but pytest is imported
# before pytest-django calls django.setup(), so the module is already loaded by
# the time these settings are read.
RUNNING_TESTS = 'test' in sys.argv or 'pytest' in sys.modules

# Neon keeps a server-side session alive briefly after the client disconnects,
# which is long enough to block `CREATE DATABASE ... TEMPLATE` and so to break
# `--parallel` entirely. See config/test_runner.py.
TEST_RUNNER = 'config.test_runner.NeonDiscoverRunner'

if RUNNING_TESTS:
    _default = DATABASES['default']
    _host = _default.get('HOST') or ''
    if '-pooler.' in _host:
        _default['HOST'] = _host.replace('-pooler.', '.', 1)
    # A persistent connection to the template is enough to block the clone.
    _default['CONN_MAX_AGE'] = 0

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# Internationalization
#
# One institution timezone is used consistently across the whole app: all
# timestamps are stored in UTC (USE_TZ=True) but every "what is today's date"
# business decision (e.g. is an event's registration window open) is derived
# via django.utils.timezone.localdate(), which converts using APP_TIMEZONE.
# This avoids the browser's local date, the server's UTC date, and the
# database's stored timestamp ever disagreeing about which calendar day it
# is for registration-window purposes.
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = config('APP_TIMEZONE', default='Asia/Kolkata')
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / media files
# ---------------------------------------------------------------------------

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Production static serving is WhiteNoise's hashed-manifest storage: every
# collected file gets a content hash in its name and a far-future cache
# header. It is only switched on when DEBUG is off, because the manifest
# only exists after `collectstatic` has run and referencing an uncollected
# file would otherwise raise during local development.
if not DEBUG:
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
    }

# Private evidence storage (participation captures, certificates). Never
# wired up to Django's static media-serving helper (see config/urls.py) —
# nothing under MEDIA_ROOT is reachable by a public URL. Files are only
# ever streamed back out through authenticated, authorized API views.
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Live participation capture (Phase 3). Centralized here rather than
# hard-coded in multiple frontend/backend locations, per project policy.
# ---------------------------------------------------------------------------

# Backend-enforced GPS accuracy ceiling. A capture reporting worse (larger)
# accuracy than this is rejected outright — see apps/participation/validation.py.
MAX_GPS_ACCURACY_METERS = config('MAX_GPS_ACCURACY_METERS', default=50, cast=int)

# Distance from the event venue beyond which a capture is flagged with
# location_warning=True. This is informational only and never blocks
# submission — Faculty (Phase 4) will see the warning during verification.
VENUE_WARNING_DISTANCE_METERS = config('VENUE_WARNING_DISTANCE_METERS', default=200, cast=int)

# ---------------------------------------------------------------------------
# Reverse geocoding (capture location -> human-readable address)
# ---------------------------------------------------------------------------
# Off by default: 'none' makes no outbound request, which is what a developer
# machine and the test suite need. Set to 'nominatim' (no key) or 'google'
# (key required) to record addresses alongside the coordinates. A failure of
# the provider never blocks a capture — see apps/participation/geocoding.py.
GEOCODING_PROVIDER = config('GEOCODING_PROVIDER', default='none')
GEOCODING_API_KEY = config('GEOCODING_API_KEY', default='')
GEOCODING_TIMEOUT_SECONDS = config('GEOCODING_TIMEOUT_SECONDS', default=3, cast=int)
# OpenStreetMap's usage policy requires callers to identify themselves.
GEOCODING_USER_AGENT = config('GEOCODING_USER_AGENT', default='SEAMS-AI/1.0')

# Maximum accepted size, in bytes, for a single capture image. Also used to
# raise Django's own request-body ceilings just enough to let an
# over-the-default-but-under-our-limit upload reach our own validation
# (which returns a clean 400/413) instead of being rejected by Django first
# with a less specific error.
MAX_CAPTURE_FILE_SIZE = config('MAX_CAPTURE_FILE_SIZE', default=8 * 1024 * 1024, cast=int)  # 8 MB
_MAX_UPLOAD_FILE_SIZE = max(
    MAX_CAPTURE_FILE_SIZE,
    config('MAX_CERTIFICATE_FILE_SIZE', default=10 * 1024 * 1024, cast=int),
)
DATA_UPLOAD_MAX_MEMORY_SIZE = _MAX_UPLOAD_FILE_SIZE + (1 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = _MAX_UPLOAD_FILE_SIZE + (1 * 1024 * 1024)

# Server-side content-type validation is authoritative (via Pillow, not the
# client-supplied Content-Type header) — see apps/participation/validation.py.
ALLOWED_IMAGE_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp']

# A certificate is a document rather than a camera capture, so it is allowed
# to be a PDF and to be somewhat larger than a photo. The type is still
# determined from the file's own bytes, never from the upload's declared
# Content-Type.
MAX_CERTIFICATE_FILE_SIZE = config('MAX_CERTIFICATE_FILE_SIZE', default=10 * 1024 * 1024, cast=int)  # 10 MB
ALLOWED_CERTIFICATE_MIME_TYPES = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp']

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/min',
        'user': '120/min',
        # Tighter limit on login/register/registration-status to slow down
        # credential-stuffing / brute-force and registration spam.
        'auth': '10/min',
        # On-request model fitting and in-memory file rendering are the two
        # most expensive things one authenticated user can make the server
        # do; bound them separately from ordinary reads.
        'ai': '30/min',
        'reports': '20/min',
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config('JWT_ACCESS_MINUTES', default=30, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_DAYS', default=7, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'SEAMS-AI API',
    'DESCRIPTION': ('REST API for event registration, participation verification, attendance, OD, '
                    'achievements, and analytics.'),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'ENUM_NAME_OVERRIDES': {
        'RoleEnum': 'apps.accounts.models.User.Role',
        'RegistrationRequestStatusEnum': 'apps.accounts.models.RegistrationRequest.Status',
        'EventStatusEnum': 'apps.events.models.Event.Status',
        'RegistrationStatusEnum': 'apps.registrations.models.Registration.Status',
        'ParticipationStatusEnum': 'apps.participation.models.Participation.Status',
        'EvidenceStatusEnum': 'apps.verification.models.Evidence.Status',
        'CaptureRoleEnum': 'apps.verification.models.EvidenceCapture.Role',
        'CaptureValidationStatusEnum': 'apps.verification.models.EvidenceCapture.ValidationStatus',
        'VerificationDecisionEnum': 'apps.verification.models.EvidenceVerification.Decision',
        # Attendance.Status and ODRequest.Status are structurally identical
        # (PENDING/APPROVED/REJECTED). drf-spectacular keys enum overrides by
        # choice set, not by model, so naming both would be a duplicate
        # definition of one enum — they deliberately share this single name.
        'ApprovalStatusEnum': 'apps.attendance.models.Attendance.Status',
        'AchievementStatusEnum': 'apps.achievements.models.Achievement.Status',
        'NotificationTypeEnum': 'apps.notifications.models.Notification.Type',
        'NotificationPriorityEnum': 'apps.notifications.models.Notification.Priority',
    },
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

# Local development accepts any origin. During development the frontend is
# served from whatever port happens to be free — 4200, 4400, or a LAN address
# when testing the live camera capture on a real phone — and keeping an
# allowlist in step with that is friction with no security benefit on a
# developer's own machine.
#
# Deployment keeps the explicit allowlist. This is tied to DEBUG rather than
# to its own environment variable so that it cannot be switched on in
# production by setting one flag, and the `if not DEBUG` block below refuses
# to start if it somehow is.
CORS_ALLOW_ALL_ORIGINS = DEBUG

# The Angular app is a separate origin from the API, so in production this is
# an explicit allowlist and never a wildcard — see
# backend/tests/test_security_configuration.py, which asserts that.
CORS_ALLOWED_ORIGINS = config(
    'CORS_ALLOWED_ORIGINS',
    default='http://localhost:4200',
    cast=Csv(),
)

# Kept on with any-origin: django-cors-headers answers a credentialed request
# by echoing the caller's Origin rather than "*", which browsers require, so
# bearer-token calls keep working from any local port.
CORS_ALLOW_CREDENTIALS = True

# Authentication is bearer-token only (see SIMPLE_JWT below): the API carries
# no session cookie, so cross-origin API calls are not CSRF-exposed. CSRF
# still matters for Django's admin and for DRF's browsable API, both of which
# are same-origin form posts, so the trusted-origin list mirrors the CORS
# allowlist by default and can be overridden when the admin is served from a
# different hostname than the API.
CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default=','.join(CORS_ALLOWED_ORIGINS),
    cast=Csv(),
)

if not DEBUG:
    if CORS_ALLOW_ALL_ORIGINS:
        raise ImproperlyConfigured(
            'CORS_ALLOW_ALL_ORIGINS must be off when DJANGO_DEBUG=False; list the deployed '
            'frontend origin(s) in CORS_ALLOWED_ORIGINS instead.'
        )
    if not CORS_ALLOWED_ORIGINS:
        raise ImproperlyConfigured(
            'CORS_ALLOWED_ORIGINS must list the deployed frontend origin(s) when DJANGO_DEBUG=False.'
        )
    if any('*' in origin for origin in CORS_ALLOWED_ORIGINS):
        raise ImproperlyConfigured('CORS_ALLOWED_ORIGINS must not contain a wildcard when DJANGO_DEBUG=False.')
    if any('*' in origin for origin in CSRF_TRUSTED_ORIGINS):
        raise ImproperlyConfigured('CSRF_TRUSTED_ORIGINS must not contain a wildcard when DJANGO_DEBUG=False.')

# ---------------------------------------------------------------------------
# Security hardening (relaxed automatically under DEBUG for local dev)
# ---------------------------------------------------------------------------

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'  # Django's default, made explicit
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'  # Django's default, made explicit
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

if not DEBUG:
    # Behind a TLS-terminating reverse proxy Django cannot see that the
    # original request was HTTPS unless the proxy forwards it; without this
    # header mapping SECURE_SSL_REDIRECT would redirect forever. Trusting the
    # header is only safe when the proxy *sets* X-Forwarded-Proto itself and
    # never passes a client-supplied one through (the deployment guide spells
    # out the nginx directive) — so it is opt-out for a deployment that
    # terminates TLS in the app process instead.
    if config('DJANGO_TRUST_PROXY_SSL_HEADER', default=True, cast=bool):
        SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = config('DJANGO_SECURE_SSL_REDIRECT', default=True, cast=bool)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ---------------------------------------------------------------------------
# Logging: never log passwords or raw tokens (see logging config below).
# ---------------------------------------------------------------------------

LOG_DIR = Path(config('DJANGO_LOG_DIR', default=str(BASE_DIR / 'logs')))

# File logging is opt-in. Under a process supervisor (systemd, Docker) the
# conventional thing is to log to stdout and let the supervisor handle
# rotation and shipping, so console is always on and files are added only
# when DJANGO_LOG_TO_FILE is set.
LOG_TO_FILE = config('DJANGO_LOG_TO_FILE', default=False, cast=bool)
if LOG_TO_FILE:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _file_handler(filename, level='INFO'):
    """A size-rotating handler; 5 x 5 MB per stream keeps disk use bounded."""
    return {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': str(LOG_DIR / filename),
        'maxBytes': 5 * 1024 * 1024,
        'backupCount': 5,
        'formatter': 'verbose',
        'level': level,
        'encoding': 'utf-8',
    }


_handlers = {
    'console': {
        'class': 'logging.StreamHandler',
        'formatter': 'verbose',
    },
}
_app_handlers = ['console']
_security_handlers = ['console']
_error_handlers = ['console']

if LOG_TO_FILE:
    _handlers['app_file'] = _file_handler('application.log')
    _handlers['security_file'] = _file_handler('security.log', level='WARNING')
    _handlers['error_file'] = _file_handler('error.log', level='ERROR')
    _app_handlers = ['console', 'app_file']
    _security_handlers = ['console', 'security_file']
    _error_handlers = ['console', 'error_file']

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': _handlers,
    'root': {
        'handlers': _app_handlers,
        'level': config('DJANGO_LOG_LEVEL', default='INFO'),
    },
    'loggers': {
        # Django's own suspicious-operation / host-header / CSRF warnings.
        'django.security': {
            'handlers': _security_handlers,
            'level': 'WARNING',
            'propagate': False,
        },
        # Unhandled exceptions inside a view. Django logs the traceback here
        # server-side while DRF returns the client a generic 500 body, so
        # internals are diagnosable without ever being sent to the caller.
        'django.request': {
            'handlers': _error_handlers,
            'level': 'ERROR',
            'propagate': False,
        },
        # This project's own authentication / authorization audit stream —
        # see apps.audit. It records *who did what to which object*; the
        # values it logs are ids, usernames, roles and action names, never a
        # password, a JWT, a refresh token, a secret or file bytes.
        'apps.security': {
            'handlers': _security_handlers,
            'level': 'INFO',
            'propagate': False,
        },
    },
}
