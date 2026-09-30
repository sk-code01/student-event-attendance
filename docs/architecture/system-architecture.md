# System Architecture

## Shape

A **modular monolith**: one Django project, one database, one deployable unit,
divided internally into apps that own their own models, permissions, services
and tests. The Angular application is a separate single-page client that talks
to it only over `/api/v1/`.

```
┌──────────────────────────────────────────────────────────────────────┐
│ Browser                                                              │
│                                                                      │
│  Angular 20 SPA            MediaDevices API  ── live camera frame    │
│   ├─ route guards (UX)     Geolocation API   ── GPS fix + accuracy   │
│   ├─ auth interceptor      IndexedDB         ── offline capture queue│
│   └─ feature areas         localStorage      ── access/refresh token │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ HTTPS, Bearer JWT
┌────────────────────────────────▼─────────────────────────────────────┐
│ Reverse proxy (nginx) — TLS termination, request size, timeouts      │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ HTTP (loopback)
┌────────────────────────────────▼─────────────────────────────────────┐
│ Gunicorn → Django 5.1 + Django REST Framework                        │
│                                                                      │
│  config/            settings, URL root, request middleware, probes    │
│  apps/<domain>/     models · serializers · permissions · services     │
│  ml/                scikit-learn model wrappers (no ORM access)       │
│  WhiteNoise         serves Django's own static files                  │
│  MEDIA_ROOT         private evidence store — never URL-routed         │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │ TLS, psycopg 3
┌────────────────────────────────▼─────────────────────────────────────┐
│ PostgreSQL (NeonDB)                                                  │
└──────────────────────────────────────────────────────────────────────┘
```

## Why a modular monolith

The workflow this system implements is a single transactional chain —
registration → participation → evidence → verification → attendance/OD →
achievement. Every step reads and writes rows the previous step created, and
several steps must be atomic with respect to each other (an evidence decision
and the notification it triggers, for example). Splitting that chain across
services would replace database transactions with distributed coordination and
buy nothing: there is one institution, one database, and no independent scaling
axis.

The module boundaries are therefore enforced in code review and package layout
rather than over a network. Each app owns its models and exposes behaviour
through a `services.py` where the workflow is non-trivial; cross-app writes go
through those services rather than through another app's models directly.

## Layers inside the backend

| Layer | Responsibility | Typical file |
|-------|----------------|--------------|
| URL routing | Maps `/api/v1/...` to views; nothing else | `config/api_urls.py`, `apps/*/urls.py` |
| View | HTTP concerns, role permission classes, queryset scoping | `apps/*/views.py` |
| Serializer | Field-level validation, explicit read-only fields (mass-assignment defence) | `apps/*/serializers.py` |
| Permission | Role and object-level authorization | `apps/accounts/permissions.py`, `apps/*/permissions.py` |
| Service | Multi-step workflow transitions, state machines, transaction boundaries | `apps/*/services.py` |
| Model | Schema, database constraints, invariants | `apps/*/models.py` |
| ML wrapper | Pure numeric functions over numpy arrays | `ml/**` |

Two rules keep this honest:

1. **Authorization is never in the frontend.** Angular route guards decide what
   to render; the DRF permission classes and the per-role querysets decide what
   exists. Every authorization test drives the API directly.
2. **The database is the last line of defence.** Uniqueness of a primary
   capture, one evidence per participation, one participation per registration,
   monotonic evidence version numbers — all of these are `CheckConstraint` /
   `UniqueConstraint` rows in migrations, not only Python checks.

## Request lifecycle

1. `SecurityMiddleware` applies the security headers and, in production, the
   HTTPS redirect and HSTS.
2. `WhiteNoiseMiddleware` short-circuits requests for collected static files.
3. `RejectNullBytesMiddleware` (`config/middleware.py`) answers `400` to any
   path or query string containing a NUL byte, which PostgreSQL text columns
   cannot store and which would otherwise surface as a `500`.
4. `CorsMiddleware` applies the explicit origin allowlist.
5. DRF authenticates the `Authorization: Bearer <access token>` header via
   simplejwt, then applies throttling, then the view's permission classes.
6. The view narrows its queryset by role *before* any aggregation, then
   delegates any state transition to its app's service layer.

## Cross-cutting concerns

**Timezone.** `USE_TZ=True`, so every timestamp is stored in UTC. Every *business*
date decision — is registration open, is today the event date — is taken with
`django.utils.timezone.localdate()` against `APP_TIMEZONE` (default
`Asia/Kolkata`). The browser's local date is never trusted for a rule.

**Notifications.** Emitted by the service layer as a side effect of a workflow
transition, with a dedupe key. A notification failure is contained so it can
never roll back the business transaction that triggered it.

**Audit.** `apps.audit` records actor, action and description for
security-relevant operations, including `REPORT_GENERATED`.

**AI.** `apps.ai` reads through `apps.analytics.scope.AnalyticsScope`, so an AI
endpoint can never see data the caller's role could not already aggregate. Every
AI function is wrapped in a failure boundary that converts any exception into a
controlled `available: false` payload — no business workflow ever calls into it,
so an AI failure has no transaction to roll back.

**Evidence storage.** Capture images live under `MEDIA_ROOT` through a
`FileSystemStorage` with `base_url=None`. `MEDIA_URL` is never routed in
`config/urls.py`, so no stored object has a public URL; the only way to read
bytes back is the authenticated, object-authorized
`GET /api/v1/evidence/captures/{id}/image/` view. Object keys are generated
server-side from ids and a UUID, never from a client-supplied filename.

## Technology choices

| Concern | Choice | Note |
|---------|--------|------|
| Backend | Django 5.1 + DRF 3.15 | Modular monolith |
| Auth | `djangorestframework-simplejwt` 5.4 | Rotation + blacklist on |
| Database | PostgreSQL via NeonDB, `psycopg` 3 | No SQLite fallback, by design |
| Schema/docs | `drf-spectacular` | Generated from code |
| Static | WhiteNoise | No static rule needed in the proxy |
| Reports | stdlib `csv`, `openpyxl`, `reportlab` | Streamed in memory |
| ML | scikit-learn 1.6, pandas, numpy | Fitted on request |
| Frontend | Angular 20, standalone components, signals | Bootstrap 5 for layout |

## What is deliberately absent

No message broker, no task queue, no cache server, no search cluster, no
container orchestrator, no GraphQL layer, no WebSocket transport, no face
recognition, and no QR-code attendance. Each of these was considered and left
out because the workload does not justify it; where the absence has a user-facing
consequence (notification latency, on-request model fitting) it is stated in the
known-limitations section of [`../FINAL_HANDOFF.md`](../FINAL_HANDOFF.md).
