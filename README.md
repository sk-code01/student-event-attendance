# SEAMS-AI

### Student Event & Attendance Management System with AI

A modular-monolith web application that records which students actually took
part in which college events — verified by a live camera capture with a GPS fix
taken at the event — and carries that evidence through faculty verification, HOD
approval, attendance and on-duty records, achievements, analytics and reporting.

**Angular 20 · Django 5.1 + DRF · PostgreSQL (NeonDB) · JWT · scikit-learn**

---

## Overview

Colleges run events constantly, and almost every downstream benefit a student
receives from attending one — being marked present, being granted on-duty leave,
having a prize recorded — depends on someone being able to answer a simple
question: *was this student actually there?*

This system answers that question with evidence rather than assertion. A student
registers for an event; on the day of the event, and only on that day, they take
a live photograph through the browser's camera while the browser reports a GPS
fix; a faculty member reviews that evidence and verifies or rejects it; and only
then can attendance, on-duty leave and achievements follow — each one a separate,
deliberate decision by the person authorized to make it.

---

## Problem Statement

Existing practice relies on paper sign-in sheets, shared spreadsheets, or a
photograph emailed after the fact. Each has the same structural weakness: the
record is created by someone who was not necessarily there, at a time that is not
necessarily the event, from evidence that cannot be checked.

That produces four concrete problems:

1. **Participation cannot be verified.** A signature or a forwarded photo proves
   nothing about presence.
2. **Records are conflated.** "Registered", "attended", "granted on-duty" and
   "won something" collapse into one list, so a registration list becomes an
   attendance record by default.
3. **Approval authority is unclear.** The person who witnessed the event and the
   person authorized to grant its consequences are often the same person, with
   no separation and no trail.
4. **Nothing is analysable.** Scattered spreadsheets cannot answer which
   departments engage, which categories draw students, or where verification is
   backing up.

---

## Objectives

1. Make participation **verifiable** — live capture, on the event date, with a
   GPS fix, reviewed by a person.
2. Keep registration, participation, attendance approval and achievement
   **permanently distinct**, in the schema and not merely in the interface.
3. **Separate authority**: Faculty verify and request; HODs approve; Admins
   administer; every step is attributable.
4. Keep an **append-only trail** — a resubmission creates a new version, an HOD
   override never erases the Faculty decision it supersedes.
5. Keep evidence **private** — no capture image is reachable without
   authorization.
6. Provide **role-scoped analytics and reports** in CSV, XLSX and PDF.
7. Provide **AI decision support** that is honest about being support and never
   makes a decision.

---

## Key Features

| | |
|---|---|
| **Accounts** | Self-registration with HOD approval, four roles, department scoping, JWT with rotation and blacklist |
| **User management** | Admin-only: search, filter and page every account; edit role and department under server-enforced invariants; activate/deactivate; password reset that also revokes the target's sessions |
| **Events** | Draft → published → cancelled lifecycle, registration windows, optional venue coordinates, college-wide events |
| **Registration** | Window-enforced, cancellable, one per student per event |
| **Live capture** | Browser camera + mandatory GPS, event-date-only, unlimited retakes, offline queue with automatic sync |
| **Evidence** | Versioned submissions, server-controlled version numbers, exactly one primary capture, SHA-256 hashed |
| **Verification** | Faculty verify / reject / request resubmission with mandatory reasons; HOD override appended, never overwritten |
| **Attendance & OD** | Two independent workflows: Faculty request, HOD approve |
| **Achievements** | Faculty create, HOD approve; only approved records are official |
| **Notifications** | Recipient derived from the business object; dedupe; 60-second polling |
| **Dashboards** | Role-specific summaries |
| **Analytics** | Ten scoped metric endpoints plus trend analysis |
| **Reports** | 12 report types × 3 formats, from a closed allowlist, streamed in memory |
| **AI** | Event recommendations, evidence risk signals, engagement clustering |
| **Audit** | Append-only trail including every report export |

---

## User Roles

| Role | Scope | Can | Cannot |
|------|-------|-----|--------|
| **Student** | Own records | Register, capture participation, view own data, export own reports | Approve anything, verify evidence, create achievements |
| **Faculty** | Authorized scope | Verify evidence, request attendance and OD, create achievements | **Approve** attendance/OD/achievements, manage events |
| **HOD** | Own department | Everything above, plus manage events, override verification, approve attendance/OD/achievements, approve registrations | Act outside their department |
| **Admin** | System-wide | Everything, plus user management, departments, colleges, HOD provisioning, the audit log | Read another user's personal notifications; demote or deactivate the last remaining Admin |

Role checks live in the API. Angular's route guards are UX only.

---

## Complete Workflow

```
  Admin ──creates──► Department, College
    │
    └──provisions──► HOD
                      │
  Student ─register──►│ approves ──► account active
                      │
                      ├──creates──► Event ──publishes──► visible to students
                      │                                        │
  Student ────────────────────────register for event ◄─────────┘
                                          │
                        ON THE EVENT DATE ▼
                          live camera capture + GPS fix
                                          │
                                  Evidence (version 1)
                                          │
  Faculty ───────────────────────────── review
              ┌───────────────┬──────────────────┐
           VERIFY          REJECT        REQUEST RESUBMISSION
              │                                   │
              │                            new version, same rules
              ▼
  Faculty ──requests──► Attendance ──┐
  Faculty ──requests──► OD Request ──┼──► HOD approves / rejects
  Faculty ──creates───► Achievement ─┘
              │
              ▼
   Notifications · Dashboards · Analytics · Reports · AI decision support

  HOD may override any Faculty verification decision. The override is
  appended; the Faculty decision is never erased; the effective decision
  governs everything downstream.
```

### The distinction that governs the whole design

> **Registration ≠ Participation ≠ Attendance Approval ≠ Achievement.**
>
> Registering is intent. Participation is evidence. Attendance approval is a
> decision. An achievement is a separate record. None of them produces the next
> one automatically — each requires a deliberate act by the person authorized to
> perform it, and the database is shaped so that skipping one is impossible
> rather than merely discouraged.

---

## Architecture

```
Browser (Angular 20 SPA)
   │  camera · geolocation · IndexedDB offline queue
   │  HTTPS, Bearer JWT
   ▼
nginx  — TLS termination, request limits, SPA routing
   ▼
Gunicorn → Django 5.1 + DRF          (modular monolith)
   │   apps/    models · serializers · permissions · services
   │   ml/      scikit-learn wrappers, no ORM access
   │   media/   private evidence store, never URL-routed
   ▼
PostgreSQL (NeonDB), TLS
```

One deployable unit, one database, no message broker, no task queue, no cache
server, no container orchestrator. The workflow is a single transactional chain,
and splitting it across services would replace database transactions with
distributed coordination for no benefit.

Detail: [`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md).

---

## Technology Stack

**Backend** — Django 5.1.5, DRF 3.15.2, `djangorestframework-simplejwt` 5.4.0,
`psycopg` 3.2.4, `dj-database-url`, `django-cors-headers`, `drf-spectacular`,
`django-filter`, `python-decouple`, Pillow, `openpyxl`, `reportlab`, WhiteNoise,
Gunicorn (production only).

**AI/ML** — scikit-learn 1.6.1, pandas 2.2.3, numpy 2.2.2.

**Frontend** — Angular 20.3 (standalone components, signals), RxJS 7.8,
Bootstrap 5.3, TypeScript 5.9.

**Testing** — pytest + pytest-django + factory-boy + pypdf + flake8;
Karma + Jasmine headless Chrome.

**Database** — PostgreSQL on NeonDB. No SQLite fallback, in any environment.

---

## AI/ML Features

Four analytical components, all **decision support only**. No AI function writes
to the database, no business service imports the AI layer, and every AI entry
point is wrapped in a failure boundary that turns any exception into a controlled
`available: false` response.

| Model | Purpose | What the output *is* |
|-------|---------|---------------------|
| **K-Nearest Neighbours** | Rank open events by similarity to a student's history | A **similarity** in (0, 1] — **not a probability**. With no history, a documented deterministic cold-start ranking, labelled as such |
| **Isolation Forest** | Flag evidence whose metadata is unusual | An **internal risk signal** — **not proof of fraud**, and never grounds for rejection. Levels are percentiles of the current population |
| **K-Means** | Cluster students by engagement | A **description of counts** — **not an academic judgment**. Labels are ordered by a documented formula, never by arbitrary cluster id |
| **Statistical trends** | Period-over-period change, direction, moving average | Plain arithmetic, not a model |

There is **no ground-truth validation dataset**, so no accuracy, precision or
recall is claimed. There is **no face recognition and no image analysis** — the
models never see an image.

Detail: [`docs/architecture/ai-architecture.md`](docs/architecture/ai-architecture.md).

---

## Live Participation Capture

The feature that makes participation verifiable rather than claimed.

- Valid **only on the event's exact date** — compared against the capture's own
  device timestamp, so a late sync of a same-day capture still counts and a
  wrong-day capture never does.
- One **primary live capture** mandatory; additional captures optional.
- **Camera frames only** — `getUserMedia` plus a canvas frame grab. There is no
  file picker, so gallery upload is not possible.
- **GPS mandatory.** A missing accuracy value is treated as *unknown*, never as
  perfect. Accuracy worse than the threshold blocks submission.
- **Venue distance is a warning**, never a rejection.
- **Unlimited retakes** before submission.
- **Offline capture queues** in IndexedDB and syncs automatically; no token is
  ever stored in the queue, and the queue is scoped to the authenticated user.
- **Both timestamps kept** — device capture time and server receipt time.
- **No QR attendance. No face recognition.**

**HTTPS is mandatory**, not advisory: browsers expose the camera and geolocation
APIs only in a secure context (HTTPS or `localhost`).

Detail: [`docs/architecture/live-capture-architecture.md`](docs/architecture/live-capture-architecture.md).

---

## Security

| Area | Measure |
|------|---------|
| Authentication | JWT, 30-minute access, 7-day refresh, rotation + blacklist on use, server-side logout |
| Authorization | Role permission classes, role-scoped querysets applied **before** aggregation, object-level checks. The JWT role claim is never the decision — the database row is |
| IDOR | Out-of-scope records return `404`, never `403`, so an id cannot probe for existence |
| Mass assignment | Every server-set field is read-only and silently ignored if posted |
| Uploads | Content type from the decoded bytes, not the header; size and dimension bounds; SHA-256; server-generated object keys, so a client filename never touches a path |
| Evidence privacy | `MEDIA_URL` never routed, storage `base_url=None`, retrieval only via an authenticated object-authorized endpoint, streamed `no-store` |
| Input | NUL bytes rejected before any view; parameterised ORM queries; hardened pagination; closed report registry |
| Transport | HTTPS required; HSTS, secure cookies, SSL redirect automatic when `DEBUG=False` |
| Headers | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, `Cross-Origin-Opener-Policy` on every response |
| CORS | Explicit allowlist; the app **refuses to start** with a wildcard in production |
| Configuration | A dev secret key, a wildcard host or a wildcard origin with `DEBUG=False` is a startup failure, not a warning |
| Throttling | Separate scopes for anonymous, authenticated, auth, AI and report traffic |
| Logging | Passwords, JWTs, refresh tokens, secrets and connection strings are never logged |
| Audit | Append-only, including every report export |

Detail: [`docs/testing/security-testing.md`](docs/testing/security-testing.md).

---

## Database

**PostgreSQL on NeonDB**, addressed by a single `DATABASE_URL`, TLS enforced
unconditionally. There is deliberately **no SQLite fallback**: a missing
`DATABASE_URL` is a startup error, because a second engine would let migrations,
constraints and transaction semantics diverge from production.

Business invariants are enforced by database constraints, not only in Python —
one active HOD per department, one registration per student per event, one
participation per registration, one evidence per participation, unique version
numbers, exactly one primary capture per version.

All timestamps are stored in UTC; every *business day* decision uses
`APP_TIMEZONE`.

Detail: [`docs/database/database-architecture.md`](docs/database/database-architecture.md)
and [`docs/database/entity-relationship.md`](docs/database/entity-relationship.md).

---

## Project Structure

```
backend/
  config/            settings, URL root, middleware, health probes
  apps/              16 Django apps (accounts … ai), each with its own tests
  ml/                scikit-learn wrappers - no ORM access
  tests/             cross-app security and lifecycle suites
  media/             private evidence store (gitignored, never web-served)
  requirements.txt · requirements-dev.txt · requirements-prod.txt

frontend/
  src/app/core/      services, guards, interceptors, models
  src/app/features/  feature areas, lazy-loaded per route
  src/app/shared/    secure-image, notification bell, charts, validators
  src/environments/  environment.ts (dev) · environment.prod.ts (build)

deploy/              gunicorn.conf.py · nginx.conf.sample · ssepams.service
docs/                architecture · api · database · testing · deployment · user-guides
.env.example         every environment variable, with safe placeholders
```

---

## Prerequisites

| | Version |
|---|---|
| Python | 3.11+ (developed on 3.13) |
| Node.js | 20+ |
| PostgreSQL | A NeonDB project (free tier is sufficient) |
| Browser | A current Chrome, Edge, Firefox or Safari — for camera and GPS |

---

## Local Development Setup

```bash
git clone <repository-url>
cd Smart_Students_Event_Attendace
```

### Environment Variables

```bash
cp .env.example backend/.env
```

Edit `backend/.env`. The two that must be right before anything works:

```ini
DATABASE_URL=postgresql://user:password@ep-xxxx.<region>.aws.neon.tech/dbname?sslmode=require
DJANGO_SECRET_KEY=<generate one>
```

Generate a secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

Every variable is documented inline in [`.env.example`](.env.example).

### Database Setup

1. Create a project at [neon.tech](https://neon.tech).
2. Copy the connection string from its dashboard into `DATABASE_URL`.
3. Keep `?sslmode=require`; use the **pooled** endpoint (hostname containing
   `-pooler`) for the application.

There is no local-database alternative. If `DATABASE_URL` is unset the
application stops with an explicit message rather than falling back.

### Backend Setup

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements-dev.txt
python manage.py migrate
python manage.py runserver          # http://localhost:8000
```

Create the first HOD (an HOD cannot depend on another HOD's approval), after
creating the department:

```bash
python manage.py provision_hod \
    --username hod_cse --email hod.cse@example.edu \
    --password '<strong password>' --department CSE
```

Optional demo data — **development only**; the command refuses to run with
`DJANGO_DEBUG=False`:

```bash
python manage.py seed_demo_data            # --reset to rebuild
```

It creates a college, two departments, an Admin, two HODs, two Faculty, five
students, five events (including one happening today), registrations, and
evidence in every reviewable state — verified, rejected, awaiting review and
HOD-overridden. Every account it creates is prefixed `demo_` and shares the
published password `DemoPass123!`, which is why it is barred from production.

### Frontend Setup

```bash
cd frontend
npm install
npm start                            # http://localhost:4200
```

`localhost` is treated as a secure context by browsers, so camera and GPS work
in development without TLS.

---

## Running Tests

```bash
# Backend (from backend/, virtualenv active)
pytest                                   # full suite
pytest apps/verification                 # one app
pytest --create-db                       # rebuild the test DB after a model change

python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python -m flake8 .

# Frontend (from frontend/)
npm test -- --watch=false --browsers=ChromeHeadless
npx tsc -p tsconfig.app.json --noEmit
npm audit --omit=dev
```

The backend suite runs against the real Neon database, so it takes considerably
longer than a local one would. Current results:
[`docs/testing/test-results.md`](docs/testing/test-results.md).

---

## Production Build

```bash
# Frontend
cd frontend && npm ci && npm run build      # → dist/frontend/browser/

# Backend
cd backend
pip install -r requirements-prod.txt
python manage.py collectstatic --noinput
python manage.py check --deploy             # must report no issues
```

---

## Deployment

nginx → Gunicorn → Django, with NeonDB as a managed database. No Docker, no
Kubernetes, no broker. Configuration files are in [`deploy/`](deploy/).

Full sequence: [`docs/deployment/deployment-guide.md`](docs/deployment/deployment-guide.md).
Pre-go-live: [`docs/deployment/production-checklist.md`](docs/deployment/production-checklist.md).
When something breaks: [`docs/deployment/troubleshooting.md`](docs/deployment/troubleshooting.md).

**HTTPS is not optional.** Live capture does not function without it.

---

## API Documentation

- Interactive Swagger UI — `http://localhost:8000/api/v1/docs/`
- OpenAPI schema — `http://localhost:8000/api/v1/schema/`
- Conventions — [`docs/api/api-overview.md`](docs/api/api-overview.md)
- Authentication — [`docs/api/authentication.md`](docs/api/authentication.md)
- Every endpoint — [`docs/api/endpoint-reference.md`](docs/api/endpoint-reference.md)

The schema is generated from the code, so it cannot drift from the
implementation.

---

## User Documentation

- [Student guide](docs/user-guides/student-guide.md)
- [Faculty guide](docs/user-guides/faculty-guide.md)
- [HOD guide](docs/user-guides/hod-guide.md)
- [Administrator guide](docs/user-guides/admin-guide.md)

---

## Known Limitations

Stated plainly rather than implied.

**Verification is assisted, not tamper-proof**

- The device capture timestamp is client-supplied. It is bounded against
  implausible future values, but a modified client could report a different
  time. There is no cryptographic capture attestation.
- GPS coordinates are likewise client-reported and can be spoofed by a modified
  browser. This is precisely why venue distance warns rather than blocks, and
  why a human verifies the evidence.
- The IndexedDB offline queue is **not encrypted**. On a shared or compromised
  device, a queued image and its coordinates could be read before upload.

**Architecture**

- Evidence is stored on the **local filesystem**. It is private and
  authorization-gated, but it is single-host: running two application servers
  requires shared storage. The storage abstraction exists so a private object
  store can replace it in one module.
- Notifications use **60-second polling**, not WebSockets. Up to a minute of
  latency is expected.
- Analytics run as **application queries**, not from a warehouse. Fine at this
  scale; a very large dataset would want pre-aggregation.
- AI models are **fitted on request**. Always current, but it makes the AI
  endpoints the most expensive reads in the system, which is why they have their
  own throttle scope.
- JWTs are stored in `localStorage` — a documented trade-off, with the
  reasoning and mitigations in
  [`docs/api/authentication.md`](docs/api/authentication.md#client-side-token-storage--a-stated-trade-off).

**Deliberately not built**

- `Registration` has no `CONFIRMED` state — the rules never asked for one.
- There is **no `CertificateArtifact` model.** Certificates remain separate and
  optional, and this phase does not implement one.
- **No browser end-to-end test suite** in this repository.
- **No AI accuracy metrics**, because there is no ground truth to measure
  against.
- **No face recognition. No QR-code attendance.** Neither is a gap; both were
  excluded by design.

---

## Future Enhancements

Listed as possibilities, not commitments.

- Private object storage (S3/GCS/Azure Blob) behind the existing abstraction —
  removes the single-host constraint.
- `HttpOnly` refresh cookies with an in-memory access token, replacing
  `localStorage`.
- WebSocket or server-sent-event notifications, replacing polling.
- A browser end-to-end suite (Playwright) covering the camera and GPS workflow
  against real browser permission prompts.
- Client-side encryption of the offline capture queue.
- Certificate artefacts as `Evidence 1 → 0..1 CertificateArtifact`, reusing the
  private storage and authenticated retrieval path.
- Scheduled dependency CVE scanning in CI.
- Pre-aggregated analytics if the dataset outgrows live queries.

---

## Project Status

**Complete.** All ten phases are implemented, tested and documented.

| | |
|---|---|
| Backend | Django REST API, 16 apps, 68 test files |
| Frontend | Angular 20 SPA, 50 spec files, 301 specs |
| Production configuration | Environment-driven, fail-fast on unsafe settings |
| Deployment | nginx + Gunicorn + systemd, documented end to end |
| Documentation | Architecture, API, database, testing, deployment, four user guides |

Current verification results, with the exact commands that produced them:
[`docs/testing/test-results.md`](docs/testing/test-results.md).
Final handoff: [`docs/FINAL_HANDOFF.md`](docs/FINAL_HANDOFF.md).
