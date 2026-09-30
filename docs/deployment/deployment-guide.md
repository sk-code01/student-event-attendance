# Deployment Guide

A reproducible production deployment for a single Linux host: **nginx →
Gunicorn → Django**, with **PostgreSQL on NeonDB** as a managed service.

There is no Docker, no Kubernetes, no message broker, no cache server and no
task queue in this deployment, because the workload does not need any of them.
The complete production surface is one service unit, one nginx site, one
directory of static files and one private media directory.

Configuration files referenced below live in [`../../deploy/`](../../deploy/).

---

## 0. HTTPS is mandatory, not recommended

Live participation capture **cannot function over plain HTTP**. Browsers expose
`navigator.mediaDevices.getUserMedia` (camera) and
`navigator.geolocation.getCurrentPosition` (GPS) only in a *secure context* —
HTTPS or `localhost`. Over HTTP the camera service raises `insecure-context` and
capture is blocked with an explicit message.

So: obtain a certificate before anything else. A deployment without TLS is not a
partial deployment of this system; it is a non-functional one.

---

## 1. Prerequisites

| | Minimum |
|---|---|
| OS | Linux with systemd (Ubuntu 22.04+ / Debian 12+ assumed below) |
| Python | 3.11+ (developed and tested on 3.13) |
| Node.js | 20+ (build machine only — not needed on the server) |
| nginx | 1.22+ |
| Database | A NeonDB PostgreSQL project |
| TLS | A certificate for your hostname (Let's Encrypt/certbot is fine) |
| RAM | 1 GB for a small deployment; 2 GB comfortable |

---

## 2. Create the service account and lay out the application

```bash
sudo adduser --system --group --home /opt/ssepams ssepams
sudo mkdir -p /opt/ssepams /var/www/ssepams
sudo chown -R ssepams:ssepams /opt/ssepams

sudo -u ssepams git clone <repository-url> /opt/ssepams
```

Target layout:

```
/opt/ssepams/backend/          Django project
/opt/ssepams/backend/venv/     virtualenv
/opt/ssepams/backend/.env      secrets, chmod 600
/opt/ssepams/backend/media/    private evidence store — never web-served
/opt/ssepams/backend/staticfiles/  collectstatic output, served by WhiteNoise
/opt/ssepams/deploy/           gunicorn.conf.py, nginx.conf.sample, ssepams.service
/var/www/ssepams/              Angular production build
```

---

## 3. Install the backend

```bash
cd /opt/ssepams/backend
sudo -u ssepams python3 -m venv venv
sudo -u ssepams ./venv/bin/pip install --upgrade pip
sudo -u ssepams ./venv/bin/pip install -r requirements-prod.txt
```

`requirements-prod.txt` is `requirements.txt` plus Gunicorn. (Gunicorn is kept
separate because it needs POSIX `fcntl` and so cannot run on a Windows
development machine.)

---

## 4. Configure the environment

```bash
sudo -u ssepams cp /opt/ssepams/.env.example /opt/ssepams/backend/.env
sudo chmod 600 /opt/ssepams/backend/.env
sudo -u ssepams nano /opt/ssepams/backend/.env
```

Generate a real secret key:

```bash
./venv/bin/python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

Production values:

```ini
DJANGO_SECRET_KEY=<the generated value>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=events.example.edu
DATABASE_URL=postgresql://user:password@ep-xxxx.<region>.aws.neon.tech/dbname?sslmode=require
DB_CONN_MAX_AGE=60
APP_TIMEZONE=Asia/Kolkata
CORS_ALLOWED_ORIGINS=https://events.example.edu
DJANGO_LOG_LEVEL=INFO
```

**The application refuses to start** — with an explicit `ImproperlyConfigured`
message, not a silent misconfiguration — if, with `DJANGO_DEBUG=False`:

- `DJANGO_SECRET_KEY` is missing or still the development fallback;
- `DJANGO_ALLOWED_HOSTS` is empty or contains `*`;
- `CORS_ALLOWED_ORIGINS` is empty or contains `*`;
- `CSRF_TRUSTED_ORIGINS` contains `*`;
- `DATABASE_URL` is missing (this one applies in every environment — there is no
  SQLite fallback).

That is deliberate: a startup failure is a far better outcome than a running
server with a wildcard host or a known secret key.

### Same-origin vs. split-origin

The nginx sample serves the Angular app and the API from **one origin**, which
is why `environment.prod.ts` uses the relative base URL `/api/v1`. In that
layout the browser never makes a cross-origin request and CORS is not exercised
at all — but `CORS_ALLOWED_ORIGINS` must still be set, because it is validated
at startup and because it is the value that applies if you later split the
origins.

If you do serve the frontend from a different hostname, set
`CORS_ALLOWED_ORIGINS` to that origin, set `CSRF_TRUSTED_ORIGINS` to the API's
own origin, and change `apiBaseUrl` in `environment.prod.ts` to the absolute API
URL before building.

---

## 5. Migrate and collect static files

```bash
cd /opt/ssepams/backend
sudo -u ssepams ./venv/bin/python manage.py migrate
sudo -u ssepams ./venv/bin/python manage.py collectstatic --noinput
sudo -u ssepams ./venv/bin/python manage.py check --deploy
```

`check --deploy` must report **no issues**. If it flags `security.W009`, the
secret key is too short or still looks generated — replace it.

`collectstatic` is required. With `DEBUG=False` the application uses WhiteNoise's
hashed-manifest storage, and a missing manifest is a runtime error — the Django
admin and Swagger UI will fail to load until it has run.

---

## 6. Provision the first HOD

An HOD cannot depend on another HOD's approval, so the first one is created from
the server:

```bash
sudo -u ssepams ./venv/bin/python manage.py provision_hod \
    --username hod_cse \
    --email hod.cse@example.edu \
    --password '<a strong password>' \
    --department CSE
```

The department must already exist (create it via the Django admin or an Admin
account). Afterwards, Admins can provision further HODs through
`POST /api/v1/users/provision-hod/`.

> **Never run `manage.py seed_demo_data` on a production host.** It refuses to
> run with `DJANGO_DEBUG=False`, but do not try to work around that: its
> accounts use a published password.

---

## 7. Build and deploy the frontend

On a build machine with Node.js (not necessarily the server):

```bash
cd frontend
npm ci
npm run build          # defaults to the production configuration
```

Output lands in `frontend/dist/frontend/browser/`. Copy its contents to the
server:

```bash
rsync -av --delete frontend/dist/frontend/browser/ user@server:/var/www/ssepams/
sudo chown -R www-data:www-data /var/www/ssepams
```

The production build substitutes `environment.prod.ts`, which sets
`apiBaseUrl: '/api/v1'` and `production: true`. **No localhost URL exists in a
production build** — verify with
`grep -r "localhost:8000" /var/www/ssepams/` (it must return nothing).

---

## 8. Run the backend under systemd

```bash
sudo cp /opt/ssepams/deploy/ssepams.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ssepams
sudo systemctl status ssepams
```

Gunicorn binds to `127.0.0.1:8000` only — it is never reachable from the
internet directly. Worker count, thread count and timeouts come from
[`../../deploy/gunicorn.conf.py`](../../deploy/gunicorn.conf.py) and can be
tuned with environment variables without editing the file.

> **Size the workers against the Neon connection limit.** Database connections
> are roughly `workers × threads`. Check your Neon plan's limit and use the
> **pooled** endpoint (the hostname containing `-pooler`) for the application.

---

## 9. Configure nginx

```bash
sudo cp /opt/ssepams/deploy/nginx.conf.sample /etc/nginx/sites-available/ssepams
sudo nano /etc/nginx/sites-available/ssepams     # hostname + certificate paths
sudo ln -s /etc/nginx/sites-available/ssepams /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

What the configuration does, and why each part matters:

| Concern | Setting | Reason |
|---------|---------|--------|
| TLS termination | `listen 443 ssl`, TLSv1.2+ | Camera and GPS need a secure context |
| HTTP redirect | `return 301 https://…` | With ACME challenges left reachable |
| API forwarding | `location ~ ^/(api\|admin\|static)/` → `127.0.0.1:8000` | Everything else is the SPA |
| Forwarded protocol | `proxy_set_header X-Forwarded-Proto $scheme` | **Must be `set`, not passed through** — Django trusts this header; `$scheme` overwrites any client-supplied value |
| Request size | `client_max_body_size 12m` | Slightly above the 8 MB capture limit, so an over-size upload gets Django's clear `400` rather than nginx's opaque `413` |
| Timeouts | 120 s body/read/send | An 8 MB photo over a phone uplink is slow |
| SPA routing | `try_files $uri $uri/ /index.html` | Angular client-side routes are not files |
| Cache | 1 year immutable for hashed assets, `no-store` for `index.html` | Hashed filenames are immutable; a cached `index.html` would keep loading the previous deploy |
| **Media** | **no `location /media/` block** | Evidence is private. Do not add one. |

---

## 10. Verify the deployment

```bash
curl -fsS https://events.example.edu/api/v1/health/        # 200, database: ok
curl -fsS -o /dev/null -w '%{http_code}\n' \
     https://events.example.edu/api/v1/health/ready/       # 200

# Evidence must not be reachable without authentication
curl -s -o /dev/null -w '%{http_code}\n' \
     https://events.example.edu/media/participation_captures/anything.jpg   # 404

# HTTP must redirect
curl -s -o /dev/null -w '%{http_code}\n' http://events.example.edu/         # 301
```

Then, in a browser: load the app, log in, and confirm that opening the live
capture page prompts for camera and location permission. If it reports an
insecure context, TLS is not terminating where the browser can see it.

---

## Evidence storage

Capture images are stored on the **local filesystem** under
`backend/media/participation_captures/`, through
`apps/participation/storage.py`.

What makes that safe:

- `MEDIA_URL` is never routed in `config/urls.py`, and the nginx configuration
  has no `/media/` location — there is no web path to the directory.
- The storage is constructed with `base_url=None`, so no stored object can even
  produce a URL.
- Object keys are generated server-side from ids and a UUID; a client-supplied
  filename is discarded entirely.
- The only way to read the bytes is
  `GET /api/v1/evidence/captures/{id}/image/`, after an object-level
  authorization check.

**Deployment requirements this creates:**

1. `backend/media/` must be writable by the service user and **nothing else**
   (`chmod 750`, owned by `ssepams`).
2. It must **not** be inside any directory nginx serves.
3. It must be **backed up separately from the database**. A database backup does
   not contain the images.
4. It is **local to one host**. Running two application servers requires shared
   storage (NFS or an object store) — a second host would not see the first
   host's files.

**Moving to private object storage** (S3/GCS/Azure Blob) is a change to
`apps/participation/storage.py` alone; that is why the abstraction exists. The
replacement must keep the same three properties: no public ACL, no presigned
URL handed to clients, and retrieval only through the authenticated endpoint.
That work is not done in this phase and is listed as a future enhancement.

---

## Logging

Gunicorn writes to stdout/stderr, which systemd captures into the journal:

```bash
sudo journalctl -u ssepams -f
sudo journalctl -u ssepams --since "1 hour ago" -p err
```

Django's logging separates three streams — application (root),
`django.security` + `apps.security` (authentication and authorization events),
and `django.request` (unhandled view exceptions, with the traceback
server-side only). Setting `DJANGO_LOG_TO_FILE=True` additionally writes
`application.log`, `security.log` and `error.log` into `DJANGO_LOG_DIR`, each
rotating at 5 MB × 5. Under systemd the journal is usually enough.

**Passwords, JWTs, refresh tokens, `Authorization` headers, the secret key and
the database password are never logged**, at any level. The Gunicorn access log
format deliberately omits headers and bodies.

---

## Updating a running deployment

```bash
cd /opt/ssepams && sudo -u ssepams git pull

cd backend
sudo -u ssepams ./venv/bin/pip install -r requirements-prod.txt
sudo -u ssepams ./venv/bin/python manage.py migrate
sudo -u ssepams ./venv/bin/python manage.py collectstatic --noinput
sudo -u ssepams ./venv/bin/python manage.py check --deploy

sudo systemctl restart ssepams

# frontend, from the build machine
rsync -av --delete frontend/dist/frontend/browser/ user@server:/var/www/ssepams/
```

`systemctl restart` is a brief interruption. For a zero-downtime reload with a
compatible migration, `systemctl reload ssepams` sends `HUP` and Gunicorn cycles
its workers gracefully.

---

## Backups

| What | How |
|------|-----|
| Database | Neon point-in-time restore; set the retention your institution requires in the Neon console |
| Evidence images | `backend/media/` — **your responsibility**, e.g. `restic`/`rsync` to off-host storage on a schedule |
| Configuration | `backend/.env` — store the secret key somewhere recoverable; losing it invalidates every issued token |

Test a restore before you need one. A backup nobody has restored is a hypothesis.
