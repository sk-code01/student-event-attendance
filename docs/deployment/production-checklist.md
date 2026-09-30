# Production Checklist

Work through this before opening the system to real users. Items marked
**BLOCKING** must be satisfied — the application enforces several of them at
startup and will refuse to run.

---

## Configuration

- [ ] **BLOCKING** `DJANGO_DEBUG=False`.
- [ ] **BLOCKING** `DJANGO_SECRET_KEY` is a freshly generated random value, unique to this deployment, not the development fallback. *(Startup fails otherwise.)*
- [ ] **BLOCKING** `DJANGO_ALLOWED_HOSTS` lists the exact hostnames, with no `*`. *(Startup fails otherwise.)*
- [ ] **BLOCKING** `DATABASE_URL` points at the production Neon database with `sslmode=require`. *(Startup fails if missing.)*
- [ ] **BLOCKING** `CORS_ALLOWED_ORIGINS` lists only the real frontend origin(s), with no `*`. *(Startup fails otherwise.)*
- [ ] `CSRF_TRUSTED_ORIGINS` is set if the admin is served from a different hostname than the API.
- [ ] `APP_TIMEZONE` matches the institution's calendar.
- [ ] `backend/.env` is `chmod 600`, owned by the service user, and **not** tracked by git.
- [ ] `python manage.py check --deploy` reports **no issues**.

## HTTPS

- [ ] **BLOCKING** A valid TLS certificate is installed and the site loads over HTTPS. *Live capture does not work without it — the browser will not grant camera or GPS access in an insecure context.*
- [ ] HTTP redirects to HTTPS (`301`), with ACME challenge paths left reachable.
- [ ] Certificate auto-renewal is configured and has been tested (`certbot renew --dry-run`).
- [ ] nginx sets `X-Forwarded-Proto $scheme` — **set, not passed through** from the client.
- [ ] HSTS is active (`SECURE_HSTS_SECONDS = 31536000`, subdomains, preload) — automatic when `DEBUG=False`.
- [ ] A browser check confirms the camera page requests permission rather than reporting an insecure context.

## Database

- [ ] Migrations applied: `manage.py migrate` completes; `migrate --plan` then shows no pending operations.
- [ ] `manage.py makemigrations --check --dry-run` reports **no changes detected**.
- [ ] The application uses Neon's **pooled** endpoint (hostname containing `-pooler`).
- [ ] `workers × threads` (Gunicorn) is within the Neon connection limit.
- [ ] Neon point-in-time restore retention is set to your institution's requirement.
- [ ] **A restore has actually been tested**, not just configured.

## Evidence storage

- [ ] **BLOCKING** `backend/media/` is **not** inside any directory nginx serves, and the nginx site has **no** `location /media/` block.
- [ ] `backend/media/` is owned by the service user with mode `750`.
- [ ] `curl https://<host>/media/participation_captures/<any name>` returns `404`.
- [ ] An evidence image request without an `Authorization` header returns `401`.
- [ ] An evidence image request from a different student returns `404`.
- [ ] `backend/media/` is included in an **off-host backup schedule**. *A database backup does not contain the images.*
- [ ] If more than one application server is planned, shared storage is in place — local filesystem storage is single-host.

## Static files

- [ ] `manage.py collectstatic --noinput` has run on this release. *(Required: with `DEBUG=False` the hashed manifest must exist or the admin and Swagger UI fail.)*
- [ ] The Angular production build was deployed from `frontend/dist/frontend/browser/`.
- [ ] `grep -r "localhost:8000" /var/www/ssepams/` returns nothing.
- [ ] `index.html` is served with `Cache-Control: no-store`; hashed assets with a long `immutable` max-age.
- [ ] Deep-linking works: loading `https://<host>/events/1` directly renders the app rather than `404`.

## Accounts and access

- [ ] The first HOD was created with `manage.py provision_hod`, with a strong password.
- [ ] Departments and colleges have been created with their real names and codes.
- [ ] **No demo data exists.** `manage.py seed_demo_data` refuses to run with `DEBUG=False`; confirm no `demo_` usernames exist in the production database.
- [ ] No test or placeholder accounts remain active.
- [ ] Django admin is reachable only to those who should have it; consider restricting `/admin/` by IP at the proxy.

## Security verification

- [ ] `python manage.py check --deploy` — clean.
- [ ] The security test suite passes against this build (`pytest backend/tests/`).
- [ ] No secret, connection string, token or private key is committed — `pytest backend/tests/test_security_configuration.py` asserts this over the whole repository.
- [ ] An unauthenticated request to a protected endpoint returns `401`.
- [ ] A student's token cannot read another student's evidence, attendance, OD, achievement or notifications (`404`).
- [ ] An HOD cannot act on another department's records (`404`).
- [ ] Faculty cannot approve attendance or OD (`403`).
- [ ] Students cannot create achievements or verify evidence (`403`).
- [ ] Every response carries `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin`.
- [ ] Report downloads carry `Cache-Control: no-store` and a sanitized filename.

## Operations

- [ ] `systemctl enable ssepams` — the service starts on boot.
- [ ] `GET /api/v1/health/` returns `200` with `database: "ok"`.
- [ ] `GET /api/v1/health/ready/` returns `200`, and `503` when the database is unreachable.
- [ ] Monitoring polls `/api/v1/health/ready/` (readiness), not `/health/` (liveness), for traffic routing.
- [ ] Log output reaches the journal: `journalctl -u ssepams`.
- [ ] Log retention is configured (`journald` or `DJANGO_LOG_TO_FILE` + rotation).
- [ ] A spot check of the logs shows **no** password, JWT, refresh token or connection string.
- [ ] Disk space is monitored — evidence images accumulate and are never deleted by the application.

## Functional smoke test on the live deployment

Run the whole chain once with real accounts:

- [ ] Self-register a student → the HOD receives a notification → approve → the student can log in.
- [ ] HOD creates an event → publishes it → the student sees it.
- [ ] The student registers for the event.
- [ ] On the event date, the student opens live capture: camera and GPS permissions are requested, a capture is taken, and submission succeeds.
- [ ] Faculty sees the evidence in the queue, views the image, and verifies it.
- [ ] Faculty requests attendance and OD; HOD approves both.
- [ ] Faculty creates an achievement; HOD approves it.
- [ ] Notifications arrive for each step and the unread count is correct.
- [ ] Analytics numbers are consistent with what was just created.
- [ ] A report exports correctly in CSV, XLSX and PDF.
- [ ] The three AI panels render, or state clearly that there is insufficient data.

## Before handover

- [ ] Someone other than the implementer has followed [`deployment-guide.md`](deployment-guide.md) end to end.
- [ ] The HOD and Admin credentials are stored in the institution's password manager, not in a file on the server.
- [ ] Administrators know where [`troubleshooting.md`](troubleshooting.md) is.
- [ ] The known limitations in [`../FINAL_HANDOFF.md`](../FINAL_HANDOFF.md) have been read and accepted by whoever owns the system.
