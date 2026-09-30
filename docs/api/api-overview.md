# API Overview

## Base URL and versioning

Every endpoint lives under a single versioned prefix:

```
/api/v1/
```

The version is in the path, not a header, so a URL in a log or a bug report is
unambiguous. There is currently one version.

## Live, generated documentation

The OpenAPI schema is generated from the code by drf-spectacular, so it cannot
drift from the implementation:

| | |
|---|---|
| Swagger UI | `GET /api/v1/docs/` |
| OpenAPI schema (YAML) | `GET /api/v1/schema/` |

Both are reachable without authentication; the schema describes the API, it does
not expose data. Where this documentation and the schema disagree, the schema is
right.

## Authentication

All endpoints require authentication except:

| Endpoint | Why |
|----------|-----|
| `POST /api/v1/auth/token/` | Issues the tokens |
| `POST /api/v1/auth/token/refresh/` | Exchanges a refresh token |
| `POST /api/v1/auth/token/verify/` | Validates a token |
| `POST /api/v1/auth/register/` | Self-registration |
| `POST /api/v1/auth/registration-status/` | Lets an applicant check their own request |
| `GET /api/v1/health/`, `GET /api/v1/health/ready/` | Operational probes |
| `GET /api/v1/schema/`, `GET /api/v1/docs/` | API documentation |

Everything else requires `Authorization: Bearer <access token>`. DRF's default
permission class is `IsAuthenticated`, so a new endpoint is private unless it
deliberately opts out — the safe default. See
[`authentication.md`](authentication.md).

## Authorization model

Four roles: `STUDENT`, `FACULTY`, `HOD`, `ADMIN`.

Authorization is applied at three levels, and all three are enforced on the
server:

1. **Role** — DRF permission classes (`IsStudent`, `IsFaculty`, `IsHOD`,
   `IsAdminRole`, `IsHODOrAdmin`).
2. **Queryset scope** — each view narrows its queryset by role *before* any
   filtering or aggregation, so an out-of-scope row is never loaded. Asking for
   someone else's id produces a `404`, not a `403` leaking its existence.
3. **Object-level** — `has_object_permission` for department and ownership
   checks on a specific record.

**The role in the JWT is never the authorization decision.** The token carries a
role claim for the client's convenience; the backend reads the authoritative
role from the database row on every request. Angular's route guards are UX only.

## Request and response conventions

- **Content type** — `application/json`, except capture upload, which is
  `multipart/form-data`, and report export, which returns a binary attachment.
- **Timestamps** — ISO-8601 in UTC (`2026-09-17T06:30:00Z`). Dates that
  represent a *business day* (`event_date`, `registration_end_date`,
  `achievement_date`) are plain `YYYY-MM-DD` and are interpreted in
  `APP_TIMEZONE`.
- **Server-set fields** are read-only in the serializer and silently ignored if
  sent — `created_by`, `requested_by`, `reviewed_by`, `status`, every
  `*_at` timestamp, `version_number`, `sha256_hash`,
  `server_received_timestamp`. This is the mass-assignment defence, and it is
  covered by `backend/tests/test_mass_assignment.py`.

### Pagination

List endpoints use page-number pagination, 20 per page:

```
GET /api/v1/events/?page=2
```
```json
{ "count": 57, "next": "...?page=3", "previous": "...?page=1", "results": [ … ] }
```

### Filtering, search and ordering

List endpoints use `django-filter`. Query parameters may only **narrow** what
the caller's role already permits — they can never widen it. Passing another
student's id yields a `404`, not their data.

### Errors

| Status | Meaning |
|--------|---------|
| `400` | Validation failed. Body is `{"field": ["message"], …}` or `{"detail": "message"}` |
| `401` | Missing, malformed or expired access token |
| `403` | Authenticated, but the role may not perform this action |
| `404` | Not found **or** outside the caller's scope — deliberately indistinguishable |
| `405` | Method not allowed |
| `429` | Throttled (see below) |
| `503` | Readiness probe only: a dependency is not ready |

Error bodies never contain a stack trace, a SQL fragment, a file path, a
connection string or any other internal detail. With `DEBUG=False` an unhandled
exception returns a generic `500` while the full traceback goes to the server
log.

### Throttling

| Scope | Rate | Applies to |
|-------|------|-----------|
| `anon` | 20/min | Unauthenticated requests |
| `user` | 120/min | Authenticated requests |
| `auth` | 10/min | Login, registration, registration-status — slows credential stuffing and signup spam |
| `ai` | 30/min | The three AI endpoints — on-request model fitting is expensive |
| `reports` | 20/min | Report export — in-memory rendering is expensive |

Exceeding a limit returns `429` with a `Retry-After` header.

### Security headers

Every response carries `X-Frame-Options: DENY`,
`X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` and
`Cross-Origin-Opener-Policy: same-origin`. Report downloads and evidence images
additionally carry `Cache-Control: no-store`.

## CORS

`CORS_ALLOWED_ORIGINS` is an explicit allowlist read from the environment.
`CORS_ALLOW_ALL_ORIGINS` is never enabled, and the application refuses to start
if a wildcard origin is configured with `DJANGO_DEBUG=False`.

## Endpoint families

| Prefix | Area |
|--------|------|
| `/auth/` | Token issue/refresh/verify, self-registration, logout |
| `/users/` | Current user, password change, registration-request review, HOD provisioning, and Admin user management (list, search, edit, activate/deactivate, password reset) |
| `/departments/`, `/colleges/` | Reference data |
| `/events/` | Event lifecycle |
| `/registrations/` | Student registration for events |
| `/participations/` | Participation records and capture eligibility |
| `/evidence/` | Versioned evidence, captures, verification, HOD override |
| `/attendance/`, `/od/` | The two independent post-verification approval workflows |
| `/achievements/` | Achievement records and their approval |
| `/notifications/` | In-app notifications, unread count, mark-read |
| `/dashboard/`, `/activity/`, `/audit/` | Per-role summary, activity feed, audit trail |
| `/analytics/` | Ten role-scoped metric endpoints |
| `/reports/` | The 12-report allowlist, preview and export |
| `/recommendations/`, `/anomalies/`, `/engagement/` | AI decision support |
| `/health/`, `/health/ready/` | Liveness and readiness probes |

Full detail: [`endpoint-reference.md`](endpoint-reference.md).
