"""
Gunicorn configuration for the Smart Student Event Participation and
Attendance Management System.

Run from the `backend/` directory:

    gunicorn config.wsgi:application -c ../deploy/gunicorn.conf.py

Every value below can be overridden by an environment variable so the same
file works on a small VM and a larger host without being edited.
"""

import multiprocessing
import os


def _int(name, default):
    return int(os.environ.get(name, default))


# Bind to loopback only. TLS termination and public exposure are the reverse
# proxy's job; Gunicorn should never be reachable directly from the internet.
bind = os.environ.get('GUNICORN_BIND', '127.0.0.1:8000')

# Sync workers are the right default here: the workload is short, database-bound
# request handling with no long-lived connections. Threads give each worker some
# concurrency while waiting on Neon without multiplying the process count.
#
# IMPORTANT: total database connections is roughly `workers x threads`. Check
# that against the Neon connection limit and lower these before raising them.
workers = _int('GUNICORN_WORKERS', min(multiprocessing.cpu_count() * 2 + 1, 9))
threads = _int('GUNICORN_THREADS', 2)
worker_class = 'gthread'

# Longer than a normal request needs, but long enough for the two genuinely
# slow endpoints: PDF/XLSX report rendering and on-request model fitting.
timeout = _int('GUNICORN_TIMEOUT', 60)
graceful_timeout = _int('GUNICORN_GRACEFUL_TIMEOUT', 30)

# Slightly above the proxy's keepalive so the proxy, not Gunicorn, closes idle
# connections.
keepalive = _int('GUNICORN_KEEPALIVE', 5)

# Recycle workers periodically. Bounds the effect of any slow memory growth in
# a long-running process; the jitter stops every worker restarting at once.
max_requests = _int('GUNICORN_MAX_REQUESTS', 1000)
max_requests_jitter = _int('GUNICORN_MAX_REQUESTS_JITTER', 100)

# Logs go to stdout/stderr so the process supervisor owns rotation and
# shipping. The access log deliberately omits the request body and every
# header: an Authorization header in a log file is a leaked credential.
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(M)sms'

# Trust the reverse proxy's forwarded headers only from loopback.
forwarded_allow_ips = os.environ.get('GUNICORN_FORWARDED_ALLOW_IPS', '127.0.0.1')

proc_name = 'ssepams'
