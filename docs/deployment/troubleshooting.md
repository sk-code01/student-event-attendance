# Troubleshooting

Symptoms first, because that is what you have when something breaks.

---

## The application will not start

Several failures here are **deliberate**: the settings module refuses to start
rather than run misconfigured. The message names the variable.

| Message | Cause | Fix |
|---------|-------|-----|
| `DATABASE_URL is required.` | No `DATABASE_URL`, in any environment | Set it in `backend/.env` to the Neon connection string. There is no SQLite fallback by design. |
| `DJANGO_SECRET_KEY must be set to a real, random secret…` | `DEBUG=False` with the development fallback key | `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"` |
| `DJANGO_ALLOWED_HOSTS must list the deployment hostnames…` | Empty with `DEBUG=False` | List the real hostnames |
| `DJANGO_ALLOWED_HOSTS must not contain a wildcard…` | `*` present with `DEBUG=False` | Replace with explicit hostnames |
| `CORS_ALLOWED_ORIGINS must list the deployed frontend origin(s)…` | Empty with `DEBUG=False` | Set the real frontend origin |
| `…must not contain a wildcard…` (CORS/CSRF) | `*` present | Replace with explicit origins |

**`ModuleNotFoundError: No module named 'decouple'`** (or another dependency) —
the virtualenv is not active or dependencies are not installed:
`./venv/bin/pip install -r requirements-prod.txt`.

**`systemctl status ssepams` shows the service flapping** — read the real error:
`journalctl -u ssepams -n 100 --no-pager`. Almost always one of the above, or
`.env` not readable by the service user.

---

## Database

**`connection to server … failed` / `could not translate host name`**

- Is `DATABASE_URL` correct and complete, including `?sslmode=require`?
- Is the Neon project awake? A free-tier project suspends when idle; the first
  request after suspension can time out while it resumes. Retry once.
- Can the host reach Neon at all? `nc -vz ep-xxxx.<region>.aws.neon.tech 5432`.

**`FATAL: too many connections for role`**

`workers × threads` exceeds the Neon connection allowance. Either lower
`GUNICORN_WORKERS`/`GUNICORN_THREADS`, or lower `DB_CONN_MAX_AGE` so idle
connections are released sooner, or use Neon's **pooled** endpoint (hostname
containing `-pooler`).

**`relation "…" does not exist`** — migrations have not been applied:
`manage.py migrate`. If `migrate --plan` shows nothing pending, you are
connected to a different database than you think; print
`DATABASES['default']['HOST']` and check.

**Tests fail with `database "test_…" is being accessed by other users`**

Neon's pooler can hold a session open after the client disconnects, which blocks
`DROP DATABASE` at teardown. `pytest.ini` sets `--reuse-db` to avoid create/drop
entirely. After changing a model, run `pytest --create-db` once to rebuild.

**Intermittent connection errors during a long test run** — these are Neon
transient pooler issues, not application defects. Re-run the specific test in
isolation to confirm before treating it as a regression. Never report a suite as
green while a failure is unexplained; classify it first.

---

## The camera or GPS does not work

This is the single most common deployment problem, and it has one main cause.

**"Camera access requires a secure connection"**

`window.isSecureContext` is false. Browsers expose `getUserMedia` and
`getCurrentPosition` only over HTTPS or `localhost`. Check:

- The site really is served over HTTPS end to end (a padlock in the address bar).
- nginx sets `proxy_set_header X-Forwarded-Proto $scheme` — **set, not passed
  through**. If Django thinks the request was HTTP it will redirect, and the
  redirect chain can land the browser on an insecure origin.
- No mixed content: an HTTPS page loading an HTTP API is blocked.

**"Camera access was denied" / "Location access was denied"**

The user declined the browser prompt, or it was previously declined and the
browser now refuses silently. The user must re-grant it in the site permissions
(padlock icon → Site settings). There is no application-side bypass, by design.

**"No camera was found"** — no video input device, or the OS denied browser
access to the camera (macOS/Windows privacy settings).

**"The camera is already in use"** — another application holds the device.
Close it and retry.

**"Location accuracy (N m) does not meet the required precision"**

A genuine GPS quality problem, not a bug. Indoors, or on a desktop using
Wi-Fi-derived location, accuracy is often 100–2000 m against a 50 m threshold.
Move outside or use a phone. If the threshold is wrong for your campus, raise
`MAX_GPS_ACCURACY_METERS` deliberately — and understand that it weakens the
evidence.

**"This capture was not taken on the event date"**

Working as intended. A capture is valid only on the event's exact date, compared
against the *device capture timestamp's* local date in `APP_TIMEZONE`. Check that
`APP_TIMEZONE` matches your institution and that the device clock is roughly
correct.

---

## Authentication

**Everything returns `401` right after login**

- Is the client sending `Authorization: Bearer <token>`?
- Has the 30-minute access token expired without a refresh? The Angular
  interceptor refreshes automatically; a non-browser client must do it itself.
- Was the refresh token already rotated? Rotation blacklists the old one — a
  replayed refresh token is rejected on purpose.

**A user cannot log in and is told their account is pending**

Their registration request has not been approved. An HOD (their department) or
an Admin approves at `GET /api/v1/users/registration-requests/`.

**"This account has been deactivated"** — `is_active = False`. Re-activate via
the Django admin or an Admin account.

**A newly deactivated user still seems to work** — they should not; DRF loads
the user on every request and rejects an inactive one. If you see this, confirm
you changed the right row and that the request really is hitting this
deployment.

---

## Authorization

**`404` where you expected data**

This is usually correct behaviour. Out-of-scope records return `404`, never
`403`, so an id cannot be used to probe for existence. Check the acting user's
role and department.

**Faculty cannot approve attendance or OD** — correct. Faculty *request*; HOD
*approves*. The separation is the point.

**A student cannot create an achievement** — correct. Faculty, HOD and Admin
create achievements; students never do.

**An HOD cannot act on an event from another department** — correct. HOD scope
is their own department. Only an Admin is system-wide.

---

## Evidence images

**An image will not load in the browser but the API returns `200`**

Evidence images cannot be loaded with a plain `<img src>` — the endpoint
requires an `Authorization` header. The `secure-image` component fetches the
blob through `HttpClient` and creates an object URL. If you are testing by
pasting the URL into the address bar, a `401` is the expected result.

**`404` for an image you can see in the evidence detail** — the object-level
check failed: the acting user is not in scope for that evidence.

**`500` on upload, or the file is missing on disk** — `backend/media/` is not
writable by the service user, or the disk is full. Check `df -h` and the
directory's ownership. With systemd hardening, `ReadWritePaths` must include the
media directory.

---

## Static files and the SPA

**The Django admin or Swagger UI renders unstyled, or `500`s**

`collectstatic` has not run for this release. With `DEBUG=False` the app uses
WhiteNoise's hashed-manifest storage and a missing manifest entry is a hard
error. Run `manage.py collectstatic --noinput` and restart.

**A deep link like `/events/1` returns nginx's `404`**

The `try_files $uri $uri/ /index.html;` fallback is missing or the API/admin
location block is shadowing it.

**Users see an old version after a deploy**

`index.html` was cached. It must be served with `Cache-Control: no-store`;
hashed assets may be cached for a year because their names change.

---

## Performance

**Everything is slow, uniformly** — round-trip latency to Neon. Deploy the
application in the same region as the Neon project; keep `DB_CONN_MAX_AGE` above
0 so connections are reused.

**Report export times out** — PDF and XLSX rendering is in-memory and grows with
row count. Narrow the report with filters. Gunicorn's timeout is 60 s by
default; raise `GUNICORN_TIMEOUT` if a legitimate export needs longer.

**An AI endpoint is slow or `429`s** — models are fitted on request, and the `ai`
throttle scope is 30/min per user. This is the intended cost boundary.

**A single endpoint got slow after a change** — likely a reintroduced N+1.
`apps/analytics/tests/test_query_budget.py` and
`backend/tests/test_performance_large_data.py` assert query counts; run them.

---

## Notifications

**No notifications appear** — they are emitted by the service layer as a side
effect of a workflow transition. If the transition did not happen, there is
nothing to notify about. Check the audit log for the action.

**The unread badge does not update** — the bell polls
`GET /api/v1/notifications/unread-count/` every 60 seconds; there is no
WebSocket. Up to a minute of delay is expected. A hard refresh forces it.

**Duplicate notifications** — should not happen; a unique dedupe key prevents
it. If you see duplicates, the dedupe key is not distinguishing the cases it
should, which is a real bug worth reporting.

---

## Getting more detail safely

```bash
journalctl -u ssepams -n 200 --no-pager          # recent logs
journalctl -u ssepams -p err --since today       # errors only
sudo -u ssepams ./venv/bin/python manage.py check --deploy
sudo -u ssepams ./venv/bin/python manage.py shell -c \
  "from django.db import connection; connection.ensure_connection(); print('db ok')"
```

**Do not set `DJANGO_DEBUG=True` on a production host to investigate a problem.**
It exposes settings, stack traces and SQL to anyone who triggers an error, and
it disables the HTTPS hardening. Reproduce in a development environment instead;
the server-side traceback is already in the log via the `django.request` logger.
