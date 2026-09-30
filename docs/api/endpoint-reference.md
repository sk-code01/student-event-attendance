# Endpoint Reference

Every path below is relative to `/api/v1/`. This reference is written from the
implementation; the generated OpenAPI schema at `/api/v1/schema/` is the
authority if the two ever disagree.

**Reading the Roles column.** A role listed for a write action may perform it;
a role listed for a read action sees only rows inside its own scope. `404` is
returned for a record outside the caller's scope — never `403` — so an id cannot
be used to probe for existence.

---

## Operational probes

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `health/` | none | **Liveness.** Always `200` while the process serves. Body reports `database: "ok" \| "unavailable"` as a field, so a transient database blip does not cause a restart loop. |
| GET | `health/ready/` | none | **Readiness.** `200` when the database answers, `503` when it does not — so a proxy can stop routing to an instance that cannot serve. |

Neither exposes settings, credentials, environment variables or stack traces.

---

## Authentication — `auth/`

| Method | Path | Auth | Roles | Description |
|--------|------|------|-------|-------------|
| POST | `auth/token/` | none | — | Issue access + refresh. Throttle `auth`. `401` with `account_pending` / `account_rejected` / `account_inactive` for a non-loginable account. |
| POST | `auth/token/refresh/` | none | — | Exchange a refresh token. Rotates and blacklists the old one. |
| POST | `auth/token/verify/` | none | — | Validate a token. |
| POST | `auth/register/` | none | — | Self-registration. `role` restricted to `STUDENT`/`FACULTY`; `department` required and must be active. Creates an inactive user + `PENDING` request. Throttle `auth`. |
| POST | `auth/registration-status/` | none | — | `{username, email}` → the applicant's own request status. Throttle `auth`. |
| POST | `auth/logout/` | required | all | `{refresh}` → `205`. Blacklists the refresh token. `400` if missing or invalid. |

---

## Users — `users/`

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `users/me/` | all | The authoritative current identity: `id, username, email, role, department, is_active, date_joined`. |
| POST | `users/me/password/` | all | `{current_password, new_password}`. Current password verified; new one validated by Django's validator chain. |
| GET | `users/registration-requests/` | HOD, Admin | Pending requests. HOD sees only their own department; Admin sees all. |
| POST | `users/registration-requests/{id}/approve/` | HOD, Admin | Activates the user. HOD limited to their department (`404` otherwise). |
| POST | `users/registration-requests/{id}/reject/` | HOD, Admin | **`reason` is mandatory.** |
| POST | `users/provision-hod/` | Admin | Creates an active HOD directly. Rejected if the department already has an active HOD. |

### Admin user management — `users/` (Admin only)

Every endpoint below is `IsAdminRole`. A Student, Faculty or HOD receives `403`
regardless of what the Angular router allows.

| Method | Path | Description |
|--------|------|-------------|
| GET | `users/` | Paginated list of every account. Query: `search` (username, email, first or last name), `role`, `department` (id, or `none` for accounts with no department), `status` (`active` \| `inactive` \| `all`), `ordering`. Filtering happens in the database, so cost does not grow with the number of rows filtered out. An unrecognised `role` yields an empty page, never the full list. |
| GET | `users/stats/` | `{total, active, inactive, by_role}`. Separate from the list so pagination's `count` keeps its ordinary meaning. |
| GET | `users/{id}/` | One account, plus its registration-request history. |
| PATCH | `users/{id}/` | Partial update of `email`, `first_name`, `last_name`, `role`, `department`, `is_active`. `PUT` is **not** offered. |
| POST | `users/{id}/activate/` | Activate. `400` if already active. |
| POST | `users/{id}/deactivate/` | Deactivate. `400` if already inactive. |
| POST | `users/{id}/reset-password/` | `{new_password, confirm_password}`. Hashed with `set_password()`; **no password material is returned**. Revokes the target's outstanding refresh tokens. |

**What is never writable here:** `username` (other records reference it by name
in the audit trail), `is_staff` and `is_superuser` (Django-level privileges that
belong to `createsuperuser` and the Django admin), `date_joined`, `last_login`.
Sending them is ignored rather than honoured.

**Invariants enforced on every edit and every activation** — the same code path,
so the two cannot drift apart:

- A `STUDENT`, `FACULTY` or `HOD` account must have a department.
- **One active HOD per department.** A second is refused with a `400` naming the
  incumbent, rather than an `IntegrityError` surfacing as a `500` — the database
  also has a partial unique index, so the check is belt and braces.
- **The system always keeps a usable Admin.** Demoting or deactivating the last
  active Admin is refused.
- An Admin cannot deactivate their own account.
- A Django superuser's role cannot be changed (`User.save()` forces it back to
  `ADMIN`, so accepting anything else would be a lie).

**What is never returned by any of these:** a password, a password hash, a JWT,
a refresh token, or any secret. Every mutation writes an audit entry
(`ADMIN_USER_UPDATED`, `ADMIN_USER_ACTIVATED`, `ADMIN_USER_DEACTIVATED`,
`ADMIN_PASSWORD_RESET`) recording the actor, the target and which fields
changed — never a password.

---

## Reference data

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `departments/` · `departments/{id}/` | all | List / detail. |
| POST · PUT · PATCH · DELETE | `departments/…` | Admin | Manage departments. |
| GET | `colleges/` · `colleges/{id}/` | all | List / detail. |
| POST · PUT · PATCH · DELETE | `colleges/…` | Admin | Manage colleges. |

---

## Events — `events/`

Read is open to every authenticated user; the queryset decides what each role
sees (students see published events only). Write requires HOD or Admin, and an
HOD may only act on events in their own department.

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `events/` | all | Filterable/searchable list. |
| GET | `events/{id}/` | all | Detail. |
| POST | `events/` | HOD, Admin | `created_by` is server-set. HOD's event is scoped to their department; an Admin may create a college-wide event with no department. |
| PUT · PATCH | `events/{id}/` | HOD (own dept), Admin | |
| DELETE | `events/{id}/` | HOD (own dept), Admin | |
| POST | `events/{id}/publish/` | HOD (own dept), Admin | `DRAFT` → `PUBLISHED`. Notifies eligible students. |
| POST | `events/{id}/cancel/` | HOD (own dept), Admin | Notifies registered students. |

**Validation.** `registration_start_date ≤ registration_end_date`; the
registration window must not start after the event date; `venue_latitude` /
`venue_longitude` are optional (without them, venue-distance warnings are simply
not computed).

---

## Registrations — `registrations/`

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `registrations/` | all | Student: own. Faculty/HOD: authorized scope. Admin: all. |
| GET | `registrations/{id}/` | all | Scoped. |
| POST | `registrations/` | Student | `{event}`. `student` is server-set from `request.user`. |
| POST | `registrations/{id}/cancel/` | Student (own) | Sets `CANCELLED` + `cancelled_at`. |

**Validation.** The event must be `PUBLISHED`; today (in `APP_TIMEZONE`) must be
inside the registration window; a student cannot register twice for the same
event (DB unique constraint).

> **Registration is not participation.** A `Registration` row records intent. It
> never implies attendance, verification or an achievement.

---

## Participation — `participations/`

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `participations/eligibility/?event={id}` | Student | Whether live capture is allowed right now, and if not, why. Checked before the browser asks for camera/GPS permission. |
| POST | `participations/` | Student | Opens a participation for a registration. `student`/`event` are server-derived from the registration. |
| GET | `participations/` · `participations/{id}/` | all | Scoped per role. |

A `Participation` exists only because a student actually ran the capture
workflow — never merely because a `Registration` exists. The one-to-one field on
`registration` is the database-level enforcement of that.

---

## Evidence and verification — `evidence/`

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `evidence/` | all | Student: own. Faculty: authorized scope. HOD: department. Admin: all. |
| GET | `evidence/{id}/` | scoped | Full version history, captures and the verification trail. |
| POST | `evidence/` | Student | Opens a new evidence version (first submission or a resubmission). |
| POST | `evidence/versions/{version_id}/captures/` | Student (own) | `multipart/form-data`: the image plus `capture_role`, `device_capture_timestamp`, `latitude`, `longitude`, `gps_accuracy`. Fully validated — see [live-capture-architecture](../architecture/live-capture-architecture.md#server-side-validation). |
| POST | `evidence/versions/{version_id}/submit/` | Student (own) | Marks the version submitted. Rejected without a `PRIMARY` capture. |
| GET | `evidence/captures/{id}/image/` | scoped | Streams the image after an object-level check. `Cache-Control: no-store`. The only path to the bytes. |
| POST | `evidence/{id}/verify/` | Faculty (scope), HOD, Admin | `{reason}` → decision `VERIFIED`. |
| POST | `evidence/{id}/reject/` | Faculty (scope), HOD, Admin | **`reason` mandatory.** |
| POST | `evidence/{id}/request-resubmission/` | Faculty (scope), HOD, Admin | **`reason` mandatory.** Lets the student open a new version. |
| POST | `evidence/{id}/override/` | HOD (own dept), Admin | `{decision, reason}`. Appends an override; **never overwrites the Faculty row.** |

**Invariants.**

- Version numbers are **server-controlled** and monotonic per evidence (DB
  unique constraint). A client cannot choose one.
- Exactly one `PRIMARY` capture per version (DB unique constraint); additional
  captures are unbounded.
- The verification history is **append-only**. An HOD override is a new row with
  `is_hod_override = True`; the Faculty decision it supersedes remains visible.
- The **effective decision** is derived: the HOD override if one exists,
  otherwise the Faculty decision. Downstream workflows read the effective
  decision, never the raw status.
- Rejection and resubmission reasons are mandatory at the serializer level.

---

## Attendance — `attendance/` and On-Duty — `od/`

Two independent workflows over the same shape. Neither implies the other, and
approving one never approves the other.

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `attendance/` · `od/` | all | Scoped list. |
| GET | `attendance/{id}/` · `od/{id}/` | scoped | Detail. |
| POST | `attendance/` | Faculty (scope) | `{participation}`. `requested_by` server-set, status `PENDING`. |
| POST | `od/` | Faculty (scope) | `{participation, reason}` — **`reason` mandatory.** |
| POST | `attendance/{id}/approve/` · `od/{id}/approve/` | HOD (own dept), Admin | Sets `APPROVED`, `reviewed_by`, `reviewed_at`. |
| POST | `attendance/{id}/reject/` · `od/{id}/reject/` | HOD (own dept), Admin | **`rejection_reason` mandatory.** |

**Validation.** The participation's *effective* evidence decision must be
`VERIFIED`. One attendance and one OD request per participation (DB one-to-one).
Faculty **cannot** approve — that is the whole point of the separation.

---

## Achievements — `achievements/`

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `achievements/` · `achievements/{id}/` | all | Scoped. Students see their own; only `APPROVED` rows are official. |
| POST | `achievements/` | Faculty, HOD, Admin | Faculty → `DRAFT`. HOD/Admin → `APPROVED` immediately (they already hold the approving authority; routing their own record to their own queue would be an approval loop). **Students cannot create achievements.** |
| PUT · PATCH | `achievements/{id}/` | creator, while `DRAFT` | |
| POST | `achievements/{id}/submit/` | Faculty (creator) | `DRAFT` → `PENDING_APPROVAL`. |
| POST | `achievements/{id}/approve/` | HOD (own dept), Admin | → `APPROVED`. |
| POST | `achievements/{id}/reject/` | HOD (own dept), Admin | **`rejection_reason` mandatory.** |

**Validation.** `achievement_date` must not predate the event and must not be in
the future. The link to `participation` is a plain FK, not one-to-one — one event
can legitimately yield more than one achievement.

---

## Notifications — `notifications/`

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `notifications/` | all | **Own notifications only** — including Admin. There is no endpoint that returns another user's notifications. |
| GET | `notifications/{id}/` | owner | `404` for anyone else. |
| GET | `notifications/unread-count/` | all | `{ "unread": n }`. Polled every 60 s by the notification bell. |
| POST | `notifications/{id}/read/` | owner | Marks read. |
| POST | `notifications/read-all/` | all | Marks every own notification read. |

There is **no create endpoint**. Notifications are emitted only by the service
layer, with the recipient derived from the business object, so no user can
address a notification to anyone.

---

## Dashboard, activity, audit

| Method | Path | Roles | Description |
|--------|------|-------|-------------|
| GET | `dashboard/` | all | Role-specific summary counts and recent items. |
| GET | `activity/` | all | The caller's own recent activity feed. |
| GET | `audit/` | Admin (HOD scoped where applicable) | The audit trail: actor, action, description, timestamp. Read-only — there is no write endpoint. |

---

## Analytics — `analytics/`

All ten are `GET` and all draw from `AnalyticsScope`. Student → own data;
Faculty → authorized scope; HOD → own department; Admin → system-wide. A
`student` / `department` / `event` query parameter is validated against the
caller's own scope first, so it can only narrow, never widen.

| Path | Reports |
|------|---------|
| `analytics/overview/` | Headline counts for the caller's scope |
| `analytics/events/` | Event counts by status and category |
| `analytics/registrations/` | Registration volumes and cancellation rate |
| `analytics/participation/` | Participation and submission rates |
| `analytics/verification/` | Verification outcomes and pending backlog |
| `analytics/attendance/` | Attendance approval outcomes |
| `analytics/od/` | OD approval outcomes |
| `analytics/achievements/` | Achievement counts by status |
| `analytics/departments/` | Per-department comparison (HOD sees only their own) |
| `analytics/trends/` | Period-over-period change, direction, moving average |

A rate whose denominator is zero is reported as `null` with its counts, not as
`0%` — a misleading number is worse than an absent one.

---

## Reports — `reports/`

| Method | Path | Description |
|--------|------|-------------|
| GET | `reports/` | The report types this caller may run. |
| GET | `reports/{report_type}/` | JSON preview of the rows. |
| GET | `reports/{report_type}/export/?file_format=csv\|xlsx\|pdf` | Binary attachment. Throttle `reports`. |

`report_type` and `file_format` both come from a **closed registry**
(`apps/reports/registry.py`) — never from user input used to build a path, a
module name or a filename. Reports are rendered in memory and streamed; nothing
is written to disk.

| Key | Title | Roles |
|-----|-------|-------|
| `student-participation` | Student Participation Report | all |
| `student-achievement` | Student Achievement Report | all |
| `student-attendance` | Student Attendance Report | all |
| `student-od` | Student OD Report | all |
| `event` | Event Report | Faculty, HOD, Admin |
| `registration` | Registration Report | Faculty, HOD, Admin |
| `participation` | Participation Report | Faculty, HOD, Admin |
| `verification` | Verification Report | Faculty, HOD, Admin |
| `attendance-od-summary` | Attendance/OD Summary Report | Faculty, HOD, Admin |
| `achievement` | Achievement Report | Faculty, HOD, Admin |
| `department` | Department Report | HOD (own), Admin |
| `system` | System/Admin Report | Admin |

Every export sets `Cache-Control: no-store`, a sanitized
`Content-Disposition: attachment; filename="…"` matching `[A-Za-z0-9._-]+`, and
records a `REPORT_GENERATED` audit entry. An empty report renders correctly with
headers and no rows.

---

## AI decision support

All three are `GET`, read-only, throttled at the `ai` scope (30/min), and return
`200` with `available: false` rather than an error when a model cannot run.

| Path | Roles | Returns |
|------|-------|---------|
| `recommendations/` | Student | Ranked open events with similarity scores and reasons. Cold-start path is labelled as such. |
| `anomalies/` | all, scoped | Evidence risk signals with level, score, thresholds and features. A Student sees signals on **their own evidence only**; Faculty, HOD and Admin see their own scope. An `?evidence=` id outside the caller's scope is a `404` before any model runs. |
| `engagement/` | all | Student: own label. Staff: distribution within scope. HOD/Admin: per-student rows within scope. |

Every response carries `model`, `model_version`, `feature_version`,
`score_basis`, `generated_at`, `inference_ms` and the standing disclaimer. See
[`../architecture/ai-architecture.md`](../architecture/ai-architecture.md).
