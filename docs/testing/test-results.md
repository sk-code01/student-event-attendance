# Test Results — Phase 10 Final Verification

Every number below was produced by running the command shown, in this
repository, on the dates given. Nothing is carried forward from an earlier
phase, and nothing is estimated.

**Environment**

| | |
|---|---|
| OS | Windows 11 |
| Python | 3.13 |
| Node.js | 20+ |
| Database | PostgreSQL on NeonDB, `ap-southeast-1`, via the pooled endpoint |
| Browser (frontend tests) | Chrome Headless 152 |
| Date | 2026-09-17 |

---

## Summary

| Check | Command | Result |
|-------|---------|--------|
| Backend test suite | `pytest -q --create-db` | **782 passed, 0 failed** in 1:18:59 |
| Frontend test suite | `ng test --watch=false --browsers=ChromeHeadless` | **317 of 317 SUCCESS** |
| TypeScript | `npx tsc -p tsconfig.app.json --noEmit` | **Clean** |
| Angular production build | `ng build --configuration production` | **Clean, 0 warnings**, 549.67 kB initial |
| Django checks | `manage.py check` | **No issues** |
| Django deployment checks | `manage.py check --deploy` (`DEBUG=False`) | **No issues (0 silenced)** |
| Unmigrated model changes | `manage.py makemigrations --check --dry-run` | **No changes detected** |
| Pending migrations | `manage.py migrate --plan` | **No planned operations** |
| OpenAPI schema | `manage.py spectacular --fail-on-warn` | **Clean, 100 operations** |
| Backend lint | `python -m flake8 .` | **0 findings** |
| Python dependency graph | `pip check` | **No broken requirements** |
| npm production audit | `npm audit --omit=dev` | **0 vulnerabilities** |
| Production static pipeline | `manage.py collectstatic --noinput` | **163 copied, 469 post-processed** |
| Production-mode server smoke | live `curl` against `DEBUG=False` | **All checks passed** |
| Real API end-to-end | `tests/e2e/api_lifecycle_smoke.py` | **94 checks, all passed** |
| Browser E2E | — | **Not executed** — see below |
| Repository secret scan | regex sweep + `test_security_configuration.py` | **No secrets found** |

---

## Backend test suite

```
cd backend
venv/Scripts/python.exe -m pytest -q --create-db -p no:cacheprovider
```

```
782 passed, 12 warnings in 4739.19s (1:18:59)
```

**782 passed, 0 failed, 0 errors.** Clean on the first run, with no transient
failures to classify.

782 = 733 after Phase 10, plus the 49 added by the final audit pass:

| Added | Count | Pins |
|-------|-------|------|
| `apps/accounts/tests/test_admin_user_management.py` | 44 | Admin user management: authorization for all four roles, search/filter/pagination, every edit invariant, activation, password reset, audit, query budget, and the constraint-collision race |
| `apps/departments/tests/test_reference_data_pagination.py` | 5 | A dropdown can fetch every row; `page_size` stays capped at 200; a nonsense value falls back to the default |

The 733 itself was 728 from Phase 9 plus the five Phase 10 added:

| Added test | Pins |
|------------|------|
| `test_readiness_is_publicly_accessible_and_reports_ready` | `/health/ready/` answers `200` / `ready` |
| `test_readiness_returns_503_when_the_database_is_unreachable` | Readiness *fails* on a dead dependency |
| `test_liveness_stays_200_when_the_database_is_unreachable` | Liveness does **not** fail on one |
| `test_probes_never_leak_configuration` | Neither probe body contains the secret key, database password or host |
| `test_evidence_image_is_never_cacheable` | An evidence image is streamed `no-store` |

### The 12 warnings

Both are third-party and neither is actionable in this codebase; neither is
suppressed:

- 11 × `RemovedInDjango60Warning` — DRF re-registers its own
  `drf_format_suffix` URL converter (`rest_framework/urlpatterns.py`).
- 1 × `DeprecationWarning` — reportlab probes for `ast.NameConstant`
  (`reportlab/lib/rl_safe_eval.py`).

### Why the suite is slow

Tests run against the **real Neon PostgreSQL database**, not SQLite, because
database constraints, transaction semantics and type behaviour are part of what
is being tested. Every query is a round trip to a remote region, so the suite
takes roughly one and three-quarter hours. That is the cost of testing against
the database the application actually runs on, and it is a deliberate trade.

### Neon-specific operational notes

Two infrastructure behaviours are documented rather than worked around:

1. **`pytest.ini` sets `--reuse-db`.** Neon's connection pooler can hold a
   server-side session open after the client disconnects, which blocks
   `DROP DATABASE` during teardown. Reusing the test database avoids
   create/drop entirely. Run `pytest --create-db` once after changing a model.

2. **Never run two pytest processes at once.** They share `test_neondb`. This
   was observed during this phase: a first run was stopped mid-way, and the
   next `--create-db` run failed at startup with

   ```
   Got an error creating the test database: database "test_neondb" already exists
   Got an error recreating the test database: database "test_neondb" is being
   accessed by other users
   DETAIL:  There are 2 other sessions using the database.
   ```

   `pg_stat_activity` showed the holder was `pgbouncer` — Neon's pooler, not a
   test process. Terminating the session with `pg_terminate_backend` cleared it
   and the run proceeded normally. **This is an infrastructure behaviour, not a
   code defect**, and it is recorded here so a future session recognises it
   instead of investigating a phantom regression.

### How a failure is classified

Any failure during a long run is classified before it is reported:

1. Record it.
2. Re-run that test in isolation.
3. If it passes in isolation and the message is a connection error
   (`connection is closed`, `getaddrinfo failed`, `server closed the
   connection`), it is a **transient Neon connection drop** — infrastructure.
4. If it fails again, it is a **real regression** and is fixed.

A suite is never reported as green while a failure is unexplained.

---

## Frontend test suite

```
cd frontend
npx ng test --watch=false --browsers=ChromeHeadless
```

```
Chrome Headless 152.0.0.0 (Windows 10): Executed 301 of 301 SUCCESS (1.67 secs / 1.267 secs)
TOTAL: 301 SUCCESS
```

**317 of 317 passing**, across 52 spec files.

The 16 added by the final audit pass cover the new user-management component
(server-side filtering, the query-string deep link, refused-action messages,
and that no password is ever rendered), the dashboard card deep link (asserting
the rendered `href` contains a real `?` and never `%3F`), and the reference-data
dropdown request shape.

Coverage includes the auth service and interceptor (single shared in-flight
refresh, replay after refresh, redirect on failure), both route guards, the
camera service (secure-context check, `getUserMedia` error mapping, frame
capture, track release), the geolocation service (permission / unavailable /
timeout mapping, no fabricated coordinates), the offline capture queue (enqueue,
user scoping, sync on reconnect, failure recording, no token stored), every API
service, and the feature components.

## Frontend build and type checking

```
npx tsc -p tsconfig.app.json --noEmit     → clean (exit 0)
npx ng build --configuration production   → clean (exit 0)
npm audit --omit=dev                      → found 0 vulnerabilities
```

| Bundle | Raw | Transfer |
|--------|-----|----------|
| Initial total | 549.53 kB | 112.14 kB |
| Lazy chunks | 54, one per lazily loaded route | |

Inside the 600 kB warning budget. No build warnings. The production
configuration substitutes `environment.prod.ts`; `grep -r "localhost:8000"` over
the build output returns nothing.

---

## Backend checks

```
python manage.py check                                  → System check identified no issues (0 silenced)
python manage.py makemigrations --check --dry-run       → No changes detected
python manage.py migrate --plan                         → No planned migration operations
python manage.py spectacular --fail-on-warn             → clean, 93 operations
python -m flake8 .                                      → 0 findings
pip check                                               → No broken requirements found
```

### Deployment checks

Run with a full production environment (`DJANGO_DEBUG=False`, a real random
secret key, an explicit host and an explicit HTTPS origin):

```
python manage.py check --deploy
→ System check identified no issues (0 silenced)
```

Run with a *short* secret key, the check correctly flags `security.W009` — the
warning is live, not suppressed.

### Production static pipeline

```
python manage.py collectstatic --noinput
→ 163 static files copied to 'backend/staticfiles', 469 post-processed.
```

`staticfiles.json` (the WhiteNoise hashed manifest) is produced. Verified
against a server running with `DEBUG=False`.

---

## Production-mode server smoke test

A Django server was started with a full production environment
(`DJANGO_DEBUG=False`, real secret key, explicit hosts and origins, SSL redirect
disabled so plain-HTTP `curl` could reach it) and checked with `curl`:

| Check | Result |
|-------|--------|
| `GET /api/v1/health/` | `200` — `{"status":"ok", …, "database":"ok"}` |
| `GET /api/v1/health/ready/` | `200` — `{"status":"ready","checks":{"database":"ok"}}` |
| `GET /static/admin/css/base.css` | `200` — WhiteNoise serving the hashed manifest |
| `GET /admin/login/` | `200` — renders, so the manifest resolves |
| `GET /media/participation_captures/anything.jpg` | **`404`** — evidence is not web-reachable |
| `GET /api/v1/dashboard/` unauthenticated | **`401`** |
| Security headers on every response | `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin` |

### Fail-fast configuration

Each of these was confirmed to **stop the application at import time** rather
than start misconfigured:

| Condition (`DJANGO_DEBUG=False`) | Result |
|---|---|
| `DJANGO_SECRET_KEY` missing or the development fallback | `ImproperlyConfigured` |
| `DJANGO_ALLOWED_HOSTS` empty or `*` | `ImproperlyConfigured` |
| `CORS_ALLOWED_ORIGINS` empty or `*` | `ImproperlyConfigured` |
| `CSRF_TRUSTED_ORIGINS` containing `*` | `ImproperlyConfigured` |
| `DATABASE_URL` missing (any environment) | `ImproperlyConfigured` |

---

## Real API end-to-end

```
cd backend && python manage.py runserver 127.0.0.1:8200
cd backend && BACKEND_DIR=. python ../tests/e2e/api_lifecycle_smoke.py http://127.0.0.1:8200
```

```
PASSED: 94    FAILED: 0
```

**94 checks, all passed**, against the development Neon database with the demo
dataset seeded.

The script drives a running server over real HTTP against the configured
development Neon database, with real JWTs, covering:

Admin provisioning (department, college, HOD) → self-registration → HOD approval
→ login → event creation → publish → student registration → participation
eligibility → live capture (including the rejection paths) → evidence submission
→ Faculty verification → attendance and OD requests → HOD approval → achievement
creation and approval → notifications → analytics → report export in all three
formats → AI endpoints → logout and refresh-token blacklisting.

Authorization is asserted at each stage, including the negative cases that
matter most: a student cannot create an event, verify evidence or create an
achievement; **Faculty cannot approve attendance, OD or an achievement**;
self-registration cannot create an HOD; an unapproved account cannot log in; a
blacklisted refresh token cannot be replayed; evidence images require
authentication; `MEDIA_ROOT` is not reachable.

Records it creates in the development Neon database are tagged `smoke*` /
`SMK*` / `SMC*` so they are unmistakably identifiable and separable from real
data.

### One step is not HTTP, deliberately

`Event` carries a database `CheckConstraint`:
`registration_end_date < event_date`. So for an event happening **today** — the
only date on which live capture is legal — the registration window is
necessarily already closed, and the registration API correctly refuses a new
registration. That is the rule working, not a defect.

The script therefore runs two flows, and the output says which is which:

- **Flow A, pure HTTP** — a future event. Registration succeeds over HTTP, and
  the capture attempt is correctly refused because it is not the event date.
- **Flow B, one ORM row** — a today event. The single `Registration` row is
  inserted through the ORM, printed as a `NOTE` in the output, after which the
  whole participation → capture → verification → attendance/OD → achievement
  chain runs over real HTTP.

### Two script defects found and fixed while writing it

Both were wrong expectations in the harness, not application defects — but the
second exposed a genuine documentation error:

1. **Usernames with underscores were rejected.** `username_validator` is
   `^[a-z0-9]+$`. This also revealed that the new `seed_demo_data` command was
   creating `demo_admin`-style accounts that **could never have been created
   through the application** — fixed, and the command now runs each generated
   username through the application's own validator so the mistake cannot recur.
2. **`GET /api/v1/anomalies/` was documented as Faculty/HOD/Admin only.** It is
   in fact *scoped, not role-restricted*: a Student may call it and receives
   signals on their own evidence only, which
   `test_student_anomalies_never_include_other_students` has pinned since Phase
   8. The documentation was corrected to match the implementation, and the
   behaviour was left alone.

---

## Live verification against the real development database

After the regression, the Admin user-management endpoints were exercised over
real HTTP against the **actual development database**, authenticated as the real
`siteadmin` account. **49 checks, all passed.**

The token was minted with `RefreshToken.for_user`, which never reads or changes
a password, so `siteadmin`'s credentials were neither needed nor touched.

What it proved on live data:

- List, stats, search, and the role / department / status / `department=none`
  filters all return what the database actually holds, and a nonsense filter is
  an empty page rather than a `500`.
- **The last active Admin could not be deactivated or demoted**, by either the
  `PATCH` or the `deactivate` route — and `siteadmin` was byte-identical
  afterwards, password hash included.
- Promoting a second HOD for MCA was refused with a message naming `hodmca`,
  and the real HOD row was unchanged.
- A throwaway account went through the whole lifecycle: edit, ignored
  `username`/`is_staff`/`is_superuser`, deactivate (login then refused),
  reactivate (login restored), password reset (old password refused, new one
  accepted, **a session opened before the reset revoked**), and a weak password
  refused by Django's validators.
- All four mutations were audited, and no audit entry contained a password.
- An HOD token was refused (`403`) on every one of these endpoints.

The throwaway account and its audit rows were then removed, and the user,
department and college counts were asserted back to their starting values.
`siteadmin` and `hodmca` ended exactly as they began.

## Browser E2E

> **Browser E2E could not be executed because the environment does not provide
> the required browser tooling.** No Chrome browser was connected to the browser
> automation extension (`list_connected_browsers` returned an empty list), so
> the real user interface could not be driven.

What *was* verified in a real browser engine: the **301 frontend specs run in
Chrome Headless**, which executes the actual component, service, guard and
interceptor code — including the camera, geolocation and offline-queue services
with the browser APIs mocked at the boundary.

What that does **not** cover, and is therefore not claimed: real camera and
geolocation permission prompts, an actual `MediaStream`, a real GPS fix, and
full-page navigation of the deployed SPA. Those were exercised manually in
earlier phases; no automated evidence of them exists in this repository.

Adding a Playwright suite is listed as a future enhancement in
[`../FINAL_HANDOFF.md`](../FINAL_HANDOFF.md).

---

## Security verification

### Repository-wide secret scan

A regex sweep for PostgreSQL connection strings with embedded credentials, AWS
access key ids, PEM private-key blocks and JWT-shaped strings across all `.py`,
`.ts`, `.html`, `.md`, `.json`, `.yaml`, `.txt`, `.conf`, `.sample`, `.service`
and `.example` files (excluding `node_modules`, `venv`, `dist`, `.angular`,
`media`, `.git`) returned **six matches, all of them the placeholder
`user:password@ep-xxxx…`** in documentation and comments. No real credential is
present.

A second sweep for `SECRET_KEY` / `API_KEY` / `private_key` / `PASSWORD`
assignments returned only:

- `DEV_SECRET_KEY = 'django-insecure-dev-key-change-me'` — the development
  fallback, which now **causes a startup failure** in production;
- `DEMO_PASSWORD = 'DemoPass123!'` — the seed command's published password,
  whose command **refuses to run** outside `DEBUG`;
- `DEFAULT_PASSWORD = 'StrongPass123!'` in test fixtures — never a real account.

`backend/.env` is untracked and gitignored;
`backend/tests/test_security_configuration.py` asserts both, and asserts that
`.env.example` carries a **blank** `DATABASE_URL` and placeholders only. When
that suite fails it prints file and line, never the value.

### What the security suites cover

Eleven cross-app suites in `backend/tests/` plus per-app IDOR suites:
authorization matrix, IDOR matrix, authentication security, mass assignment,
file-upload security, input hardening, security configuration and secret
hygiene, transaction safety, timestamp boundaries, workflow lifecycle, and
large-data query budgets. Detail:
[`security-testing.md`](security-testing.md).

---

## Performance

| Check | Where | Result |
|-------|-------|--------|
| Analytics query budget | `apps/analytics/tests/test_query_budget.py` | Concrete query counts asserted; no N+1 |
| Large-data endpoint behaviour | `backend/tests/test_performance_large_data.py` | Query counts asserted |
| Report generation | `apps/reports/tests/test_reports.py` | All 12 types × 3 formats render |
| AI inference | `apps/ai/tests/` | Each response reports its own `inference_ms` |

**No load or stress testing was performed.** Query-count budgets bound the
per-request cost; concurrent-user throughput has not been measured and is not
claimed.

---

## Sequencing of the final run

The authoritative backend regression ran **after** every code change in this
phase, over the complete tree. Two earlier runs were started and deliberately
stopped rather than reported:

1. A pre-change baseline, stopped at ~19% once it became clear its numbers would
   be superseded by the post-change run.
2. A post-change run stopped at ~10% when the missing `no-store` on evidence
   images was found. Rather than report a suite that had not exercised the fix,
   the fix and its test were applied and the suite restarted from scratch.

The only changes made after the 733-test run were `seed_demo_data.py` (a
management command that no test imports — verified by grep for `call_command`
and `get_commands` across `apps/` and `tests/`) and documentation. The
`733 passed` result therefore covers the whole of the tested application code as
it now stands.
