# Module Architecture

## Backend modules (`backend/apps/`)

Each app owns its models, serializers, permissions and tests. Apps that
implement a state machine also own a `services.py`, and every transition goes
through it — views never mutate another app's state directly.

| App | Owns | Key models | Mounted at |
|-----|------|-----------|-----------|
| `accounts` | Users, roles, self-registration and its approval, HOD provisioning, password change, **Admin user management** (list/search/edit/activate/deactivate/password reset) | `User`, `RegistrationRequest` | `/api/v1/auth/`, `/api/v1/users/` |
| `departments` | Academic departments | `Department` | `/api/v1/departments/` |
| `colleges` | Conducting colleges | `College` | `/api/v1/colleges/` |
| `events` | Event lifecycle (draft → published → cancelled), registration window, venue coordinates | `Event` | `/api/v1/events/` |
| `registrations` | A student's intent to attend an event | `Registration` | `/api/v1/registrations/` |
| `participation` | The fact that a student ran the live-capture workflow; eligibility; the private storage abstraction | `Participation` | `/api/v1/participations/` |
| `verification` | Versioned evidence, captures, Faculty decisions and HOD overrides | `Evidence`, `EvidenceVersion`, `EvidenceCapture`, `EvidenceVerification` | `/api/v1/evidence/` |
| `attendance` | Faculty-requested, HOD-approved attendance | `Attendance` | `/api/v1/attendance/` |
| `od` | On-Duty requests, independent of attendance | `ODRequest` | `/api/v1/od/` |
| `achievements` | Official achievement records and their approval | `Achievement` | `/api/v1/achievements/` |
| `notifications` | Recipient-derived in-app notifications with dedupe | `Notification` | `/api/v1/notifications/` |
| `dashboard` | Per-role dashboard aggregation | — | `/api/v1/dashboard/` |
| `audit` | Append-only audit trail and the user-facing activity feed | `AuditLog` | `/api/v1/audit/`, `/api/v1/activity/` |
| `analytics` | Role-scoped metrics and trend arithmetic; the single authorization boundary for all aggregation | — | `/api/v1/analytics/` |
| `reports` | The 12-report allowlist and the CSV/XLSX/PDF renderers | — | `/api/v1/reports/` |
| `ai` | Feature engineering, model orchestration, the AI failure boundary | — | `/api/v1/recommendations/`, `/anomalies/`, `/engagement/` |

### Shared / infrastructure

| Path | Purpose |
|------|---------|
| `config/settings.py` | All configuration, environment-driven; refuses to start on an unsafe production setting |
| `config/api_urls.py` | The `/api/v1/` namespace root |
| `config/middleware.py` | `RejectNullBytesMiddleware` |
| `config/views.py` | `/health/` liveness and `/health/ready/` readiness probes |
| `apps/accounts/permissions.py` | `IsStudent`, `IsFaculty`, `IsHOD`, `IsAdminRole`, `IsHODOrAdmin`, `IsOwnDepartmentHOD` |
| `apps/accounts/admin_views.py` + `admin_serializers.py` | Admin user management, kept in their own modules because they are the only place one account may change another |
| `apps/analytics/scope.py` | `AnalyticsScope` — the one place role scope is turned into a queryset |
| `apps/participation/storage.py` | `private_capture_storage` — the swap point for object storage |
| `ml/` | Pure scikit-learn wrappers. No ORM import anywhere under `ml/` |

### Dependency direction

```
        ai ──────────────► analytics ──┐
         │                             │
         └──► ml (pure numpy)          ▼
                              verification ──► participation ──► registrations ──► events
reports ──► analytics                   │                                             │
                                        ▼                                             ▼
               attendance / od / achievements                              colleges / departments
                                        │                                             │
                                        └──────────► notifications, audit ◄───────────┘
                                                             │
                                                          accounts
```

`accounts`, `departments` and `colleges` are leaves that nothing else depends
on for behaviour. `ml/` depends on nothing in `apps/` — it receives numpy arrays
and returns numpy arrays, which is what keeps the models testable without a
database.

## Frontend structure (`frontend/src/app/`)

| Path | Purpose |
|------|---------|
| `core/services/` | One typed service per API area; the only place `HttpClient` is used |
| `core/guards/auth.guard.ts` | Requires a session; redirects to `/login` |
| `core/guards/role.guard.ts` | Requires a role for a route — **UX only**, never the security boundary |
| `core/interceptors/auth.interceptor.ts` | Attaches the bearer token; refreshes once on `401` and replays, with a shared in-flight refresh so concurrent 401s do not each trigger a refresh |
| `core/models/` | Request/response interfaces mirroring the API |
| `features/auth/` | Login, self-registration, unauthorized page |
| `features/events/` | Event list, detail, create/edit form, per-event registrations, my registrations |
| `features/participation/live-capture/` | The camera + GPS capture workflow |
| `features/participation/history/` | A student's participation and evidence history |
| `features/faculty/` | Verification queue and detail, attendance/OD requests, achievement creation |
| `features/hod/` | Verification override, attendance approval, OD approval, achievement approval |
| `features/student/` | A student's attendance, OD and achievement views |
| `features/admin/` | User management, colleges, departments + HOD provisioning, system-wide oversight |
| `features/analytics/`, `features/reports/`, `features/audit/` | Role-scoped analytics, report preview/export, audit log |
| `features/ai/` | Recommendations, anomalies, engagement, and the dashboard AI panel |
| `shared/` | `secure-image` (authenticated image fetch), `notification-bell`, charts, `ai-disclaimer`, validators |

### `secure-image`

Evidence images cannot be loaded with a plain `<img src>` — the endpoint
requires an `Authorization` header. The `secure-image` component fetches the
image as a blob through `HttpClient` (so the interceptor attaches the token),
turns it into an object URL, and revokes that URL on destroy. This is why no
evidence URL is ever a shareable link.

### Routing and lazy loading

Routes are standalone-component routes with `loadComponent`, so each
feature area is its own lazy chunk: the production build emits 54 lazy chunks
against a 549.53 kB initial bundle. `auth.guard` and `role.guard` are applied per route, and
role-specific navigation is derived from the authenticated user's role as
returned by `GET /api/v1/users/me/` — never from a claim the client could edit.
