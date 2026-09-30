# Backend — SEAMS-AI

Django + Django REST Framework modular monolith. Each business domain lives
in its own app under `apps/`, added as its implementation phase begins
rather than pre-scaffolded empty.

## Structure

```
backend/
  config/          # project settings, root URLs, /api/v1/ URL namespace, health check
  apps/
    accounts/      # custom User model (role-based: STUDENT/FACULTY/HOD/ADMIN), JWT auth, registration-approval workflow
    departments/   # academic-structure unit; scopes HOD/Student/Faculty
    colleges/      # institution conducting an event (distinct from Department)
    events/        # Event model + lifecycle (draft/published/cancelled/completed)
    registrations/ # student event Registration model
    participation/ # live camera+GPS participation capture (Phase 3)
    verification/  # evidence versioning, Faculty verification, HOD override, resubmission (Phase 4)
    attendance/    # attendance requests + HOD approval, from verified participation (Phase 5)
    od/            # on-duty requests + HOD approval - independent of attendance (Phase 5)
    achievements/  # achievement records + HOD approval workflow (Phase 5)
    notifications/ # in-app notifications + the central notification service (Phase 6)
    dashboard/     # role-aware operational dashboard aggregation, no models (Phase 6)
    analytics/     # scoped aggregation + statistical trends, no models (Phase 7)
    reports/       # CSV/XLSX/PDF generation from the same scoped querysets (Phase 7)
    audit/         # minimal AuditLog for event/registration/participation/evidence lifecycle actions
    ai/            # feature extraction + decision-support API over ml/, no models (Phase 8)
  ml/              # pure numpy-in/numpy-out models: recommendation (KNN), anomaly_detection (Isolation Forest),
                   # engagement (K-Means); trend_analysis points at apps.analytics.trends (Phase 8)
  tests/           # cross-app integration tests (added as apps accumulate)
  manage.py
```

## Setup

```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements-dev.txt
copy ..\.env.example .env    # then edit values
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## Database

The authoritative target database is **NeonDB PostgreSQL**, addressed by a
single `DATABASE_URL` connection string (copy it from the Neon dashboard):

```
DATABASE_URL=postgresql://user:password@ep-xxxx.neon.tech/dbname?sslmode=require
```

The app itself (Django + Angular) always runs on your local machine — only
the database is Neon's remote/online instance.

Until `DATABASE_URL` is set, the backend falls back to a local SQLite file
so `migrate`/`pytest` are runnable without a live database. This is a setup
convenience only, not the target database — no phase is complete until it
has been validated against the real Neon database.

## API

- Base path: `/api/v1/`
- Health check: `GET /api/v1/health/`
- JWT auth: `POST /api/v1/auth/token/`, `POST /api/v1/auth/token/refresh/`, `POST /api/v1/auth/token/verify/`
- Colleges: `GET/POST /api/v1/colleges/` (public read, Admin-only write)
- Events: `GET/POST /api/v1/events/`, `GET/PATCH/DELETE /api/v1/events/{id}/`,
  `POST /api/v1/events/{id}/publish/`, `POST /api/v1/events/{id}/cancel/`
- Registrations: `GET/POST /api/v1/registrations/` (optional `?event={id}` filter for HOD/Admin),
  `GET /api/v1/registrations/{id}/`, `POST /api/v1/registrations/{id}/cancel/`
- Participation (Student-only writes; HOD department-scoped / Admin system-wide reads):
  `GET /api/v1/participations/eligibility/?event={id}` — UX check, not authoritative;
  `GET/POST /api/v1/participations/` (POST opens/idempotently re-fetches a DRAFT participation for the caller's registration);
  `GET /api/v1/participations/{id}/`. As of Phase 4, capture upload/submission/image-retrieval live entirely under
  `/api/v1/evidence/` (below) — a Participation is only ever opened here, never uploaded to directly.
- Evidence versioning + Faculty verification + HOD override (Phase 4 — see the dedicated section below for the
  full workflow/business rules):
  `GET/POST /api/v1/evidence/` (POST opens/idempotently re-fetches the current in-progress evidence version for
  the caller's own participation — the only mechanism that creates version 1, or version N+1 after a Faculty
  resubmission request);
  `GET /api/v1/evidence/{id}/` — full nested detail: student/event, every version, every capture, every
  verification decision;
  `POST /api/v1/evidence/versions/{id}/captures/` — multipart upload of one capture to an in-progress version
  (runs the exact same Phase 3 validation pipeline);
  `POST /api/v1/evidence/versions/{id}/submit/` — finalizes a version (requires a primary capture; idempotent);
  `GET /api/v1/evidence/captures/{id}/image/` — the *only* way to read a capture's image bytes back;
  `POST /api/v1/evidence/{id}/verify/`, `/reject/`, `/request-resubmission/` — Faculty decision actions (reason
  required for reject/request-resubmission, optional for verify);
  `POST /api/v1/evidence/{id}/override/` — HOD/Admin override of the current Faculty decision (`decision` +
  `reason`, both required).
- Attendance (Phase 5 - Faculty request, HOD/Admin decide; see the dedicated section below):
  `GET/POST /api/v1/attendance/` (POST = Faculty raises a request for a verified participation),
  `GET /api/v1/attendance/{id}/`,
  `POST /api/v1/attendance/{id}/approve/`, `POST /api/v1/attendance/{id}/reject/` (`reason` required).
- OD (Phase 5 - a separate workflow from attendance, never a status of it):
  `GET/POST /api/v1/od/` (POST requires `participation` + `reason`),
  `GET /api/v1/od/{id}/`,
  `POST /api/v1/od/{id}/approve/`, `POST /api/v1/od/{id}/reject/` (`reason` required).
- Achievements (Phase 5):
  `GET/POST /api/v1/achievements/`, `GET /api/v1/achievements/{id}/`,
  `PATCH /api/v1/achievements/{id}/` (draft editing by the creator only),
  `POST /api/v1/achievements/{id}/submit/` (draft -> pending approval),
  `POST /api/v1/achievements/{id}/approve/`, `POST /api/v1/achievements/{id}/reject/` (`reason` required).
- Notifications (Phase 6 - always the caller's own, no role exemption):
  `GET /api/v1/notifications/` (paginated, newest first, optional `?unread=true`),
  `GET /api/v1/notifications/{id}/`,
  `POST /api/v1/notifications/{id}/read/`, `POST /api/v1/notifications/read-all/`,
  `GET /api/v1/notifications/unread-count/`.
- Dashboard (Phase 6): `GET /api/v1/dashboard/` - one role-aware endpoint.
- Activity (Phase 6): `GET /api/v1/activity/` - the caller's own AuditLog records.
- Audit trail (Phase 6): `GET /api/v1/audit/` - HOD (own department) and Admin (system-wide) only;
  filters `action`, `actor`, `date_from`, `date_to`, `search`.
- Analytics (Phase 7 - scoped before aggregation; see the section below):
  `GET /api/v1/analytics/overview/`, `/participation/`, `/events/`, `/registrations/`,
  `/attendance/`, `/od/`, `/achievements/`, `/verification/`, `/trends/`, `/departments/`.
  Shared filters: `date_from`, `date_to`, `event`, `category`, `department`, `student`;
  `/trends/` also takes `period` (`daily`|`weekly`|`monthly`).
- Reports (Phase 7):
  `GET /api/v1/reports/` (types this caller may run),
  `GET /api/v1/reports/{type}/` (JSON preview of the exact rows),
  `GET /api/v1/reports/{type}/export/?file_format=csv|xlsx|pdf` (streamed file).
- AI decision support (Phase 8 - read-only, scoped by `AnalyticsScope`; see the section below):
  `GET /api/v1/recommendations/` (Student only; `?limit` 1-50),
  `GET /api/v1/anomalies/` (`?evidence=<id>` within scope, `?limit` 1-500),
  `GET /api/v1/engagement/`.
  Every response carries `available`, `disclaimer`, `generated_at`, `inference_ms`; `available: false`
  with `reason` `INSUFFICIENT_DATA` | `MODEL_ERROR` is a normal answer, never a 500.
- OpenAPI schema: `GET /api/v1/schema/`
- Swagger UI: `GET /api/v1/docs/`

## Event & registration business rules

- **Event lifecycle**: `DRAFT → PUBLISHED → CANCELLED`, plus `COMPLETED`
  (applied lazily — any published event whose `event_date` has passed is
  flipped to `COMPLETED` the next time the events endpoint is queried, since
  there is no scheduled job in this phase). Cancelled/completed events are
  read-only; edits are rejected by the API regardless of what the UI shows.
- **Registration window**: registration is only accepted when the event is
  `PUBLISHED` and today's date (in `APP_TIMEZONE`, see below) falls within
  `registration_start_date`–`registration_end_date`. Publishing an event does
  **not** open registration by itself. `registration_end_date < event_date`
  and `registration_start_date <= registration_end_date` are enforced as
  Postgres `CHECK` constraints, not just serializer validation.
- **No re-registration after cancellation**: `(student, event)` has an
  unconditional DB `UniqueConstraint` — once cancelled, a student cannot
  register again for the same event. Nothing in the spec requires
  re-registration support, so the simplest behavior was chosen deliberately.
- **Event cancellation does not cascade**: cancelling an event never
  modifies existing `Registration` rows. A registration stays `REGISTERED`
  even if its event becomes `CANCELLED` — the event's own status is the
  single source of truth, and the frontend surfaces both together.
- **`Event.department` is not a form field**: it's an internal-only FK to
  `departments.Department`, auto-set to the creating HOD's department (or
  `null` for Admin) purely so HOD write-authorization can reuse the existing
  Department relationship instead of a new ownership table. It is never
  accepted from request input and is not shown to students.
- **Race-condition safety**: registration creation relies on the DB unique
  constraint as the final guard — a concurrent duplicate insert raises
  `IntegrityError`, which the view catches and returns as a normal 400
  response rather than a 500.
- **Timezone**: `TIME_ZONE` (default `Asia/Kolkata`, override via
  `APP_TIMEZONE`) is the one institution timezone used for every "what is
  today" business decision, via `timezone.localdate()` — never the browser's
  local date or the server's raw UTC date. Event dates are plain calendar
  dates (`DateField`); only audit-style timestamps use full datetimes.

## Participation (live camera + GPS) business rules

**Django never accesses the device camera or GPS.** The browser is
responsible for `getUserMedia()`, the live preview, still-frame capture,
requesting geolocation permission, and reading `navigator.geolocation`'s
coordinates/accuracy/timestamp. The backend only ever receives what the
browser already collected and chooses to send — and is authoritative for
validating all of it. See `frontend/README.md` for the browser side.

- **Registration ≠ Participation**: `Participation.registration` is a
  `OneToOneField` (`Registration 1 -> 0..1 Participation`) — a row is only
  created when a student actually runs the capture workflow, never merely
  because they're registered. `student`/`event` are stored redundantly for
  query performance but are always re-derived from `registration` in
  `save()`, so they can never drift out of sync with it.
- **Two different "is this eligible" checks, on purpose**:
  `GET .../eligibility/` gates on "is today the event date" (UX only, so
  the button doesn't even appear on the wrong day while online).
  Opening a participation (`POST /participations/`) does **not** re-check
  that — a legitimately delayed offline sync (captured on the correct day,
  uploaded later) must still succeed. The one authoritative date check is
  per-capture, against that capture's own `device_capture_timestamp`
  (`validate_device_timestamp_for_event`), comparing its local calendar
  date (in `TIME_ZONE`) to `event.event_date` — never against the date the
  HTTP request happens to arrive.
- **A DRAFT participation with no successful capture does not block
  retry**: eligibility only refuses a *second* attempt once the first one
  actually reached `SUBMITTED`/`PENDING_VERIFICATION`. Opening is
  idempotent (`get_or_create` on `registration`), so retrying after a
  failed capture (e.g. bad GPS accuracy) reuses the same row rather than
  erroring or creating a duplicate.
- **GPS**: `latitude`/`longitude`/`gps_accuracy` are required on every
  capture. Missing accuracy is a hard rejection — it is never treated as
  "perfect". `gps_accuracy > MAX_GPS_ACCURACY_METERS` (default 50, env
  `MAX_GPS_ACCURACY_METERS`) is rejected outright.
- **Venue distance is a warning, never a rejection reason**: when
  `Event.venue_latitude`/`venue_longitude` are set, distance to the
  capture's coordinates is computed with a plain Haversine calculation
  (`apps/participation/geo.py`) and stored on the capture; exceeding
  `VENUE_WARNING_DISTANCE_METERS` (default 200) only sets
  `location_warning=True` for later (Phase 4) faculty review.
- **Device vs server timestamp**: `device_capture_timestamp` is
  client-supplied evidence metadata — explicitly documented as
  *not* cryptographically trustworthy (a malicious client could send
  anything; the only defense here is rejecting implausible future values).
  `server_received_timestamp` is `auto_now_add` and can never be
  overridden by the client, regardless of what the request body contains.
- **Images**: validated server-side with Pillow — real decodability (not
  just the claimed `Content-Type`), actual detected format restricted to
  `ALLOWED_IMAGE_MIME_TYPES`, size within `MAX_CAPTURE_FILE_SIZE` (default
  8MB), and reasonable pixel dimensions. A SHA-256 hash is computed and
  stored (`sha256_hash`) — duplicate-detection logic itself is left for a
  later phase, but the hash is captured now. Storage object keys are always
  server-generated (`capture_upload_path`) from the participation/student
  IDs and a UUID; a client-supplied filename is never used as, or
  incorporated into, a storage path.
- **Duplicate/idempotent submission**: `ParticipationCapture` has a partial
  unique index (`condition=Q(role='PRIMARY')`) — only one primary capture
  per participation, enforced at the DB level; a race is caught as
  `IntegrityError` and turned into a clean 400. `submit()` on an
  already-submitted participation returns the existing state instead of
  erroring, so a double-click or an offline-queue retry can't create a
  duplicate submission.
## Evidence versioning + Faculty verification (Phase 4)

Registration ≠ Participation ≠ **Evidence Submission** ≠ **Faculty
Verification** ≠ Attendance Approval ≠ Achievement — Phase 4 adds the middle
two as their own first-class concepts, distinct from Participation's own
DRAFT/SUBMITTED lifecycle:

- **Architecture**: `Participation 1 -> 1 Evidence 1 -> N EvidenceVersion
  1 -> N EvidenceCapture`, plus `EvidenceVersion 1 -> N EvidenceVerification`
  (Faculty decisions *and* HOD overrides, distinguished by `is_hod_override`
  — not two separate tables, since an override is conceptually "one more
  decision row", never a replacement of the Faculty one).
  `apps.verification.EvidenceCapture` is the direct successor of Phase 3's
  `ParticipationCapture` — the Phase 4 migration (`apps.verification.0002`)
  converted every existing capture row into `Evidence` +
  `EvidenceVersion(version_number=1)` + `EvidenceCapture`, reusing the exact
  same stored file path (no file bytes were copied or re-uploaded), before a
  later migration dropped the old table. `Participation.status` was
  simplified to `DRAFT`/`SUBMITTED` only — `PENDING_VERIFICATION` and the
  unused `verified_at` field were removed, since verification status is now
  `Evidence.status`'s job exclusively; the two are never conflated.
- **Evidence.status** is the smallest clean state model: `SUBMITTED` ->
  `UNDER_REVIEW` -> `VERIFIED` / `REJECTED` / `RESUBMISSION_REQUIRED`, and
  `RESUBMISSION_REQUIRED` -> (student resubmits) -> a *new* `SUBMITTED`
  version. The transition to `UNDER_REVIEW` happens automatically, once,
  the first time a Faculty member opens the evidence detail — it is not a
  decision itself, so it is not audit-logged (avoiding log noise), only
  actual decisions are.
- **Versioning is append-only**: `version_number` is always
  server-generated (never client-supplied), DB-uniqueness-enforced per
  evidence (`unique_version_number_per_evidence`), and previous versions
  are **never** overwritten or deleted — Version 1's captures and decision
  history remain fully readable forever, even after Version 2 exists. A new
  version is created by exactly one thing: calling `POST /api/v1/evidence/`
  again after Faculty has requested a resubmission
  (`apps.verification.services.open_evidence_version`) — a mere retake
  before the current version is ever submitted just reopens the same
  in-progress version (idempotent), it never creates a meaningless extra
  version. `REJECTED` is a **final** Faculty decision for that version —
  only `RESUBMISSION_REQUIRED` unlocks a new one.
- **The event-date rule is not weakened for resubmissions**: a resubmission
  reuses the exact same per-capture `validate_device_timestamp_for_event`
  check as the original submission — if Faculty requests a resubmission
  after the event date has already passed, the student's new live capture
  is rejected by that same unconditional check, exactly like a first-time
  capture on the wrong day would be. No exception workflow for this case
  exists in this phase; if one is ever needed, it must be added
  deliberately and documented, not silently bypassed here.
- **Effective decision, without erasing history**: when an HOD overrides a
  Faculty decision, a brand-new `EvidenceVerification` row is created with
  `is_hod_override=True` — the original Faculty row is never mutated or
  deleted. `EvidenceVersion.effective_verification` computes which one
  currently governs (an HOD override always wins if one exists, else the
  latest Faculty decision) purely by querying, never by overwriting.
- **Authorization reuses the existing convention, deliberately with no
  `FacultyEventAssignment` table**: Faculty and HOD access is scoped by
  `evidence.participation.event.department_id == user.department_id` —
  exactly the same pattern `CanAccessParticipation` already used for HOD in
  Phase 3. An evidence record outside the requester's visible queryset
  resolves to 404 (IDOR-safe — never confirms existence); a visible record
  with a forbidden action for that role (e.g. a Student calling
  `/verify/`, a Faculty member calling `/override/`, an HOD from another
  department) resolves to 403.
- **Concurrency**: `open_evidence_version` and `record_faculty_decision` /
  `record_hod_override` all take a `select_for_update()` row lock on the
  parent `Evidence` inside `transaction.atomic()` — two simultaneous
  resubmission attempts can't both create "version 2", and two simultaneous
  Faculty decisions on the same version can't both succeed (the second
  observes the evidence is no longer `SUBMITTED`/`UNDER_REVIEW` and is
  rejected). The one-`PRIMARY`-capture-per-version invariant is still a
  genuine DB `UniqueConstraint`, not just an application check.
- **Images**: `GET /api/v1/evidence/captures/{id}/image/` is the only way
  to read a capture's bytes back — same authenticated/authorized streaming
  pattern as Phase 3, gated by the same department/ownership rule as the
  parent evidence record.
- **Certificate handling was deferred**: `CertificateArtifact` (evidence's
  optional 1-to-0..1 relation, per the original spec) was not implemented
  in this phase — nothing in the required Evidence/Version/Verification/
  Override workflow depends on it, and the spec explicitly permits deferring
  it. This is a deliberate scope decision, not an oversight.

## Institutional identity fields

Every account carries `full_name` plus exactly one institution-issued
identifier, chosen by role:

| Role              | Identifier                        | Field                              |
| ----------------- | --------------------------------- | ---------------------------------- |
| Student           | University Registration Number / USN / UUCMS | `university_registration_number` |
| Faculty           | Faculty ID                        | `faculty_id`                       |
| Event Coordinator | Faculty ID                        | `faculty_id`                       |
| Admin             | none                              | both NULL                          |

**One field, not three.** A USN, a UUCMS number and a university registration
number are three names institutions use for the same value, so they share one
column. No format is imposed: hard-coding one institution's pattern would
reject every other institution's.

**Casing is normalised on write.** A Faculty ID is stored lowercase and a
university registration number uppercase, whatever case it arrives in. The
identifiers are shown back to people, so two spellings of one value would read
as two identifiers. Duplicate checks are case-insensitive either way, so the
normalisation is about display, not about uniqueness. The USN keeps its
upper-case form because that is how it appears on the documents a student
holds.

**An Event Coordinator is a faculty member.** The role describes what someone
does in this system, not a different kind of employment, so both faculty roles
are issued the same college identifier. That has a consequence worth stating:
`faculty_id` is unique across *all* users rather than within a role, so the
same person cannot hold two identities by registering once under each faculty
role. Promoting a Faculty member to Event Coordinator keeps their Faculty ID.

**The backend is the authority.** Requirements are enforced in three places,
and each catches something the others cannot:

* the Angular form shows and requires the field the selected role is issued,
  and never submits the other one;
* the registration serializer rejects every wrong combination — a Student with
  only a Faculty ID, a faculty role with only a registration number, either
  carrying both — so bypassing the form with `curl` gains nothing;
* database check constraints (`university_registration_number_is_student_only`,
  `faculty_id_is_faculty_or_coordinator`) hold against a data import or a
  future endpoint that never touches a serializer.

**Identifiers are never invented.** The columns are nullable, and the
requirement is applied at registration rather than in the schema, because an
Admin provisioning an account may legitimately not have the college's Faculty
ID to hand yet. Accounts created before these fields existed keep a NULL and
are completed administratively — nothing backfills a placeholder.

**Do not confuse these with each other.** `username` is the login handle,
`email` is an email address, `id` is the internal primary key, a department has
its own `code`, and the two fields above are institutional identifiers. They
are distinct concepts and none of them substitutes for another.

## Testing

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
```

**Use pytest.** It is not merely a preference — two things the suite depends on
live in pytest configuration and nowhere else:

* `conftest.py` clears DRF's throttle cache between test cases with an autouse
  fixture. The `auth` scope on login and register is process-wide, so without
  that fixture a run trips dozens of 429s that have nothing to do with what is
  being tested.
* `pytest.ini` sets `--reuse-db`, which skips creating and dropping the test
  database on every run.

Running `python manage.py test` bypasses both and will fail in ways that look
alarming and mean nothing. After changing a model, run `pytest --create-db`
once to rebuild the test database.

### Neon and the test database

Two pieces of this are worth knowing before you change test configuration.

**Do not pass `--parallel`.** The Django runner clones the test database once
per worker with `CREATE DATABASE ... TEMPLATE test_neondb`, and that clone
fails here every time:

```
source database "test_neondb" is being accessed by other users
DETAIL:  There is 1 other session using the database.
```

It is not a stale connection you can find and close. Probed from a clean
connection with nothing of ours running, `pg_stat_activity` reports no sessions
on the template, `pg_terminate_backend` has nothing to terminate, and the
`CREATE` is refused anyway. The holder is internal to Neon and invisible to
`neondb_owner`, which is not a superuser. `config/test_runner.py` carries the
evidence, terminates the one lingering session that *is* real, and turns the
remaining failure into an error that says to drop `--parallel`.

**Test runs bypass the connection pooler.** `DATABASE_URL` names Neon's pooled
endpoint, which is right for serving requests and wrong for tests: a pooler
holds server-side sessions open after the client disconnects, which blocks both
`CREATE DATABASE ... TEMPLATE` and the `DROP DATABASE` at teardown. `config/
settings.py` detects a test run and switches to the direct endpoint with
`CONN_MAX_AGE = 0`. `apps/accounts/tests/test_db_endpoint.py` asserts that this
is actually in effect, so the setting cannot quietly stop working.

## Attendance, OD and achievements (Phase 5)

Registration != Participation != Evidence Verification != **Attendance** != **OD**
!= **Achievement**. Phase 5 adds the last three as three independent records, each
with its own table, its own approval decision and its own audit actions.

### The eligibility rule, and why it is not `Evidence.status`

All three workflows may only start from a participation whose **effective**
verification decision is `VERIFIED`. "Effective" is the crucial word: an HOD
override always takes precedence over the Faculty decision it overrode, and the
Faculty row is never mutated. So:

| Faculty decision | HOD override | Eligible? |
| --- | --- | --- |
| (none yet) | - | No |
| `VERIFIED` | - | **Yes** |
| `REJECTED` | - | No |
| `RESUBMISSION_REQUIRED` | - | No |
| `REJECTED` | `VERIFIED` | **Yes** |
| `VERIFIED` | `REJECTED` | No |

That decision is resolved by
`apps.verification.services.get_effective_decision()` /
`is_participation_verified()`, which read
`Evidence.current_version.effective_verification` - the append-only decision
history that is the real source of truth. `Evidence.status` is a denormalized
shortcut maintained for list-view filtering and is deliberately **not** what
these workflows gate on. The check is re-run at decision time as well as at
request time, so an override landing between the Faculty request and the HOD
decision correctly blocks the approval.

### Authority model (identical for attendance and OD)

- **Faculty request.** Raising a request is a Faculty action, scoped to
  `participation.event.department_id == user.department_id`. Admin is
  deliberately excluded from raising one, exactly as Admin is excluded from
  `CanVerifyEvidence` in Phase 4: Admin inspects the workflow system-wide
  rather than impersonating a role inside it.
- **HOD decides.** Approve/reject is HOD (department-scoped) or Admin
  (system-wide). Faculty have no approval power anywhere in this phase, not
  even over a record they created themselves.
- **Students read only.** A student can see their own attendance, OD and
  achievement records with full status and rejection reasons, and can act on
  none of them.

### No automatic anything

- Verified evidence does **not** create attendance. It only makes a Faculty
  attendance *request* possible.
- Verified participation does **not** create an achievement. An achievement row
  exists only because an authorized user deliberately created one.
- Approving attendance never creates, changes or consults an OD record, and
  vice versa. There is no code path in either app that reads the other, and
  `apps.od.tests.test_independence` exists specifically to fail if one is ever
  added. OD is **not** modelled as `Attendance.status = 'OD'`.

### Records and state

`Attendance` and `ODRequest` both use `PENDING -> APPROVED / REJECTED`, with a
`OneToOneField` on `participation` - that is simultaneously the
"one record per participation" rule and the duplicate-request guard, enforced by
the database rather than an application check. No separate "final attendance"
table exists: an `APPROVED` row *is* the official record, with `reviewed_by` and
`reviewed_at` naming who made it official and when. Nothing in the finalized
requirements asks for resubmission of a rejected request, so none was invented -
a decision is final, and `REJECTED -> APPROVED` through a stale request is
refused.

`Achievement` uses `DRAFT -> PENDING_APPROVAL -> APPROVED / REJECTED`. Faculty
records land in `PENDING_APPROVAL` (or `DRAFT`, if they pass
`submit_for_approval: false` to keep editing). HOD/Admin records are `APPROVED`
on creation - they already hold the approving authority, so routing them through
their own queue would be an approval loop. Only `APPROVED` is official
(`is_official` on the serializer). `participation` is a plain ForeignKey, not a
OneToOne: one event can legitimately yield more than one achievement, and no
`unique(student, achievement_type)`-style constraint is imposed because it would
reject legitimate records.

### Neither student nor event is duplicated on these rows

`Participation` already stores both and re-derives them from its `Registration`
on every save. Copying them onto attendance/OD/achievement rows would create a
second field a malicious client could try to disagree with - the
`student=A, participation=B-belonging-to-C` spoof. The create serializers accept
only `participation` (plus `reason`/achievement fields); student and event are
read through it. A participation outside the requester's scope resolves to 404,
never a 400/403 that would confirm it exists.

### Server-generated fields

`status`, `requested_by`, `requested_at`, `reviewed_by`, `reviewed_at` and
`created_by` are read-only on every serializer in all three apps, and no
endpoint accepts a writable `status`. State changes only through the dedicated
`approve`/`reject`/`submit` actions, which take the reviewer from
`request.user` and the timestamp from the server clock. Attendance and OD expose
no `PUT`/`PATCH` at all; the achievement `PATCH` carries only descriptive fields
and is refused by the service layer unless the record is still a `DRAFT` owned
by the caller.

### Database constraints

Beyond the `OneToOneField` uniqueness above, each table carries `CheckConstraint`s
mirroring the service-layer rules so the invariants hold even against direct SQL:

- `attendance_rejection_reason_required` / `od_rejection_reason_required` /
  `achievement_rejection_reason_required` - a `REJECTED` row must carry a
  non-empty reason (blank strings are not stored as reasons).
- `attendance_review_fields_match_status` / `od_review_fields_match_status` /
  `achievement_review_fields_match_status` - a decided row always names its
  reviewer and review time; a pending/draft one never does. "Approved by nobody"
  is unrepresentable.
- `od_reason_required` - an OD request always carries the justification the HOD
  reviews.

### Concurrency

Every decision takes a `select_for_update()` row lock inside
`transaction.atomic()` and refuses anything that is no longer `PENDING`
(`PENDING_APPROVAL` for achievements). Two simultaneous approvals cannot both
succeed, a simultaneous approve and reject leave exactly one outcome, and two
simultaneous requests for the same participation cannot both create a record -
the DB unique constraint catches the loser as an `IntegrityError` that becomes a
clean 400. Each app has a `TransactionTestCase` + real-threads test for these.

### Achievement date validation

An achievement cannot predate its event (results are announced after the event,
never before) and cannot be dated in the future. Nothing stricter is imposed,
because a result can legitimately be announced days or weeks later.

### Audit actions added

`ATTENDANCE_REQUESTED`, `ATTENDANCE_APPROVED`, `ATTENDANCE_REJECTED`,
`OD_REQUESTED`, `OD_APPROVED`, `OD_REJECTED`, `ACHIEVEMENT_CREATED`,
`ACHIEVEMENT_UPDATED`, `ACHIEVEMENT_SUBMITTED`, `ACHIEVEMENT_APPROVED`,
`ACHIEVEMENT_REJECTED` - all recorded through the existing `AuditLog.record()`,
never a second audit mechanism.

## Notifications, dashboards and activity (Phase 6)

### Three separate concepts, deliberately not merged

| | What it is | Table | Audience |
| --- | --- | --- | --- |
| **AuditLog** | The authoritative business/security trail, written for every meaningful state change | `audit.AuditLog` | HOD (own department), Admin |
| **Activity** | That same trail, filtered to one user and presented readably | *(no table - a filtered read)* | Each user, their own |
| **Notification** | An addressed message with a read state, telling someone something needs attention | `notifications.Notification` | Its recipient only |

One business action can produce all three. They stay separate because reading
or dismissing a notification must never disturb the audit trail, and because
the audit trail records things nobody needs to be notified about.

**No Activity table was created.** AuditLog already stores an actor and a
timestamp for every business action, so activity is a filtered read of it.
Duplicating every audit row into a second table would double the write cost and
create two sources of truth that can disagree. If that read ever becomes a
performance problem, a denormalised feed table is the documented future
optimisation.

### Notification architecture

Everything is created through `apps.notifications.services`, which exposes
primitives (`create_notification`, `create_bulk_notifications`, `mark_read`,
`mark_all_read`, `unread_count`) and one semantic helper per business event
(`notify_registration_decision`, `notify_event_cancelled`,
`notify_evidence_decision`, `notify_attendance_request`,
`notify_attendance_decision`, `notify_od_request`, `notify_od_decision`,
`notify_achievement_pending`, `notify_achievement_decision`). No view and no
other service constructs a `Notification` directly.

**Recipients are derived, never supplied.** Each helper takes a business object
and works out who should hear about it, so no client input ever reaches
`recipient`. The serializer is entirely read-only and there is no create,
update or delete endpoint at all.

### Transaction behaviour - the central guarantee

A notification must never break the business action it describes. Two
mechanisms enforce that:

1. Call sites use `notifications.schedule(...)`, which wraps
   `transaction.on_commit`. The notification is attempted only *after* the
   academic decision has durably committed, so a rollback sends nothing and a
   notification failure cannot roll anything back.
2. Every semantic helper is wrapped by `_safe`, which logs and swallows any
   exception.

The trade-off is explicit: we would rather lose a message than lose an
approval. `test_attendance_approval_survives_a_failing_notification` asserts
exactly this by making the notification layer raise and checking the approval
still stands.

### Duplicate prevention

`Notification.dedupe_key` carries an optional idempotency key with a partial
unique index (`WHERE dedupe_key != ''`). A retried, double-clicked or
re-delivered action reuses the existing row instead of creating a duplicate.

Keys are chosen to be precise rather than broad - an evidence decision key
includes the *version number*, so a genuine second resubmission request on a
later version is still delivered while a retry of the same one is not.
Notifications that may legitimately recur leave the key blank and opt out.

### Routing safety

`action_route` only ever holds an internal Angular path. `_clean_route` drops
anything with a scheme, a protocol-relative `//` prefix, or a backslash -
dropping rather than sanitising, so a malformed route degrades to "no link"
instead of becoming an open redirect. A `CheckConstraint`
(`notification_action_route_is_internal`) enforces the same rule at the
database level, so the invariant holds even against direct SQL.

### Read state

`is_read` / `read_at`, with `read_at` always taken from the server clock; a
client cannot supply it. A `CheckConstraint` keeps the pair consistent, so
"read with no timestamp" and "unread but timestamped" are unrepresentable.
Marking read never touches `created_at`, so ordering is stable.
Notifications cannot be deleted in this phase - history is preserved.

### Notification scope

The queryset is `recipient=request.user` with **no role exemption, not even
Admin**. A notification is personal mail with a personal read state, so
system-wide visibility would mean one user marking another's mail as read.
Admin oversight lives in `/audit/` instead, which is the right tool for it.
Every cross-user access is therefore a plain 404.

### Dashboard architecture

One endpoint, `GET /api/v1/dashboard/`, role-aware server-side. There is
deliberately no `/dashboard/admin/` variant to request, so there is no path by
which a Student can ask for the Admin payload.

Scope by role: Student sees only their own records; Faculty and HOD are scoped
to their department (a staff account with no department sees zeros, not
everything department-less); Admin is system-wide. Out-of-scope data is never
computed, let alone serialized and filtered in Angular.

The response is `{role, cards, recent_activity, recent_notifications,
unread_notifications}`. `cards` is a list of `{key, label, value, route}`, so
the backend decides what a role may see and the frontend renders what arrives
rather than keeping a second per-role list that could drift out of step with
the authorization rules.

These are **operational** dashboards only - current counts, pending queues and
recent items. Trends, engagement scoring, predictions, charts and report
generation belong to Phase 7 and are deliberately absent.

**Query budget:** every count is a `.count()` or `.aggregate()` over a filtered
queryset; nothing iterates a queryset to count related rows. Two tests assert
the query count does not change when data is added, which is what would fail if
an N+1 were introduced.

### Audit access

`GET /api/v1/audit/` is HOD/Admin only - Student and Faculty get 403 rather
than an empty list, because the resource is not theirs to query. An HOD is
scoped to actions performed by members of their own department, which is the
closest honest scope available: AuditLog records an actor but not a target
entity, so scoping is by who acted.

**Known limitation (documented, not hidden):** the phase brief mentions showing
IP address, user agent and a structured entity type in the audit view.
`AuditLog` was designed in Phase 2 with only actor/action/description/timestamp,
and `AuditLog.record()` has no access to the request. Adding those fields would
mean touching every call site across Phases 2-5, and populating them only in new
code would produce filters that silently miss most records - worse than not
offering them. They are therefore not implemented. The upgrade path is to add
the fields and thread request context through `record()` as a deliberate
cross-phase change.

Nothing is redacted in the audit serializer because there is nothing sensitive
to redact: `AuditLog.record()` never stored passwords, JWTs, image bytes or GPS
values - only a short human description written by the service layer.

### Audit actions added in Phase 6

`REGISTRATION_REQUEST_APPROVED` and `REGISTRATION_REQUEST_REJECTED`. Phase 1
recorded no audit entry for registration decisions; HOD activity is derived
from AuditLog, so approvals would otherwise have been invisible there. The
approval logic itself is unchanged.

Reading a dashboard, listing notifications and marking a notification read are
**not** audited - that would make the trail unusably noisy for no traceability
gain.

## Analytics and reporting (Phase 7)

### Architecture

```
Angular -> DRF view -> AnalyticsFilters (validate + scope-check)
                    -> AnalyticsScope   (role-scoped querysets)
                    -> services/trends  (aggregate)
```

No analytics database, no warehouse, no Celery/Redis/Kafka, no new
infrastructure. Analytics is a read-only aggregation over the existing
operational tables and is never a second source of truth: it reads the same
rows the feature APIs write.

### The authorization boundary

`apps/analytics/scope.py` is the **single** place role scope is decided, and
`apps/reports` uses the same module — so a report can never contain a row the
caller could not already see through the API.

Two rules:

1. **Scope is applied before aggregation.** Each accessor returns an
   already-filtered queryset, so out-of-scope rows are excluded by the database
   and never reach Python. Aggregating everything and filtering afterwards
   would both leak data and misrepresent performance.
2. **Query parameters are never authorization.** `AnalyticsFilters` validates
   every `student`/`department`/`event` against the caller's own scope first, so
   a foreign id yields 403/404 rather than data. A caller may narrow what they
   asked for; they can never widen it.

| Role | Scope |
| --- | --- |
| Student | own records only; `?student=` other than themselves is 403 |
| Faculty | their department, matching the existing evidence/attendance/OD/achievement APIs - analytics broadens nobody's access |
| HOD | own department; naming another is 403 |
| Admin | system-wide |

A staff account with **no** department matches nothing rather than implicitly
matching every department-less event - the same null guard the Phase 5 apps use.

Department comparison (`/analytics/departments/`) is HOD (own) and Admin (all)
only; Student and Faculty get 403 rather than an empty list.

### Metric definitions

Every rate states its own denominator in the response (`*_rate_basis`), because
a rate with an unstated denominator is not a defensible metric:

- `participation_rate` = participations / **live (non-cancelled) registrations**
- `verification_rate` = verified / **decided** evidence (pending excluded)
- attendance & OD `approval_rate` = approved / **decided** (approved + rejected); pending excluded
- achievement `approval_rate` = approved / **decided**; drafts and pending excluded
- `cancellation_rate` = cancelled / all registrations

A rate whose denominator is zero returns **null, not 0.0** - "nothing was
requested" and "everything was refused" are different facts, and the UI renders
null as an em dash.

Registration, Participation, Verification, Attendance approval and Achievement
remain five distinct concepts throughout; none is derived from another.

### Verification uses the effective decision

`Evidence.status` is the denormalised effective decision - both
`record_faculty_decision` and `record_hod_override` write it, and an override
overwrites it. Aggregating on it therefore counts the decision that actually
governs, never a superseded Faculty one. Calling
`EvidenceVersion.effective_verification` per row would give the same answer as
an N+1. `test_hod_override_flips_the_effective_outcome` pins the invariant, and
override activity is reported separately so review history stays visible.

### Events and departments

`COMPLETED` is a real persisted status maintained by
`Event.objects.mark_past_events_completed()`; analytics reads it rather than
re-deriving it, so it cannot disagree with the events API.

Admin-created events belong to **no** department. They are never attributed to
one; `/analytics/departments/` reports them separately as
`department_less_events`.

### Trends and statistics

`/analytics/trends/` groups with `TruncDay`/`TruncWeek`/`TruncMonth` and returns
a chart-ready series plus plain descriptive statistics: total, average, latest,
previous, change, percentage change, direction and a 3-period trailing moving
average.

**This is statistics, not ML.** No model, no training, no persistence, no
scikit-learn import. `change_percent` is null when the previous period was zero
(growth from zero has no meaningful percentage), and the moving average is `[]`
when there is less data than the window rather than padded with partial values.

**Timezone:** `TIME_ZONE` (default `Asia/Kolkata` via `APP_TIMEZONE`) with
`USE_TZ=True`. `Trunc*` on a timezone-aware column is evaluated by Postgres in
that timezone, so a record created at 23:30 IST falls on that day - the same
rule `timezone.localdate()` applies elsewhere. `Event.event_date` is a plain
DateField and needs no conversion. The active timezone is echoed in the
response.

### Performance

Every metric is a `.count()`/`.aggregate()` with conditional `Count(filter=...)`
over a filtered queryset; nothing iterates a queryset to count related rows.
Query-budget tests assert the query count does not change when records are
added, which is exactly what an N+1 would break.

### Reports

12 report types, 3 formats. Type and format come from closed allowlists in
`apps/reports/registry.py` - never from user input used to build a path, a
module name or a filename.

| Report | Roles |
| --- | --- |
| Student Participation / Achievement / Attendance / OD | all roles (scoped) |
| Event, Registration, Participation, Verification, Attendance/OD Summary, Achievement | Faculty, HOD, Admin |
| Department | HOD (own), Admin |
| System/Admin | Admin |

**Security:**

- Rows come from `AnalyticsScope`, so a report is scoped exactly like the API.
- Rendering happens **entirely in memory**; nothing is written to disk, so no
  report lands in `MEDIA_ROOT` or any publicly reachable location and there is
  no temporary file to leak. Bytes are streamed over the authenticated request.
- Every request re-checks authorization - the UI listing is convenience only.
- Filenames are built from the allowlisted key plus a timestamp and stripped to
  `[A-Za-z0-9._-]`, so they cannot carry a path separator, a traversal
  sequence, a quote that would break the header, or a token.
- `Cache-Control: no-store` - these carry personal academic data.
- Each builder selects named columns; none serializes a model wholesale. No
  password, token, evidence object reference, storage key, file path or GPS
  value appears in any report, asserted by tests that scan generated output.

**Why `file_format` and not `format`:** DRF reserves the `format` query
parameter for renderer content negotiation (`URL_FORMAT_OVERRIDE`). With only
`json`/`api` renderers registered, `?format=csv` makes `APIView.initial()`
raise `Http404` *before authentication runs*. Renaming the parameter keeps the
collision local rather than disabling `?format=json` across every other
endpoint in the project.

**Empty data** is a valid report: CSV and XLSX keep their header row, and the
PDF states that no records matched. None of them raises.

**Format details:** CSV is UTF-8 with a BOM (so Excel opens non-ASCII names)
and CRLF line endings; XLSX has a bold frozen header row, bounded column widths
and a separate `Report Info` sheet so provenance can never be mistaken for data;
PDF is landscape A4 with wrapped cells and a header repeated on each page.

### Audit

`REPORT_GENERATED` is recorded through the existing `AuditLog` on every export,
with the report title, format, row count and filter summary - never the report
contents and never a token. Previewing is not audited: only generation is a
business action.

## AI decision support (Phase 8)

### What it is, and what it is not

Three scikit-learn models run **inside the Django process** on request, over
the existing operational tables, and return signals a person may consult:

| Signal | Model | Who | Output |
| --- | --- | --- | --- |
| Event recommendations | KNN similarity (`NearestNeighbors`), deterministic cold-start fallback | Student, own only | ranked open events + feature-backed reasons |
| Evidence risk signals | `IsolationForest(random_state=42)` | Student own / Faculty & HOD department / Admin system | LOW / MEDIUM / HIGH + the specific features that crossed a threshold |
| Engagement clusters | `KMeans(n_init=10, random_state=42)` over `StandardScaler` features | Student own label / Faculty distribution / HOD & Admin per-student rows | LOW / MODERATE / HIGH |

**The AI never decides anything.** It does not approve attendance or OD, does
not verify or reject evidence, does not create achievements, cannot override a
Faculty or HOD decision, and writes to no table. Every response carries the
disclaimer *"AI-generated decision-support signal. Final academic decisions
remain with authorized Faculty/HOD personnel."* The anomaly UI has no approve,
reject or dismiss control - its only action is a link to the existing
verification screen. There is **no face recognition, no facial embedding and no
biometric processing** of any kind: the anomaly features are capture counts,
distances, accuracies, delays and history, never image content.

No new infrastructure: no Redis, Celery, Kafka, model server, feature store or
persisted model. scikit-learn 1.6.1, numpy 2.2.2 and pandas 2.2.3 were already
in `requirements.txt`; nothing was added.

### Architecture

```
Angular -> DRF view (apps/ai/views.py)       role check, ?evidence resolved against scope -> 404
        -> apps/ai/services.py               orchestration + the failure boundary
        -> apps/ai/features.py               grouped ORM queries -> numpy matrices (identity-free)
        -> ml/<model>.py                     numpy in, numpy out, no Django import
```

`ml/` is pure: it raises `ValueError`/`InsufficientData` and never touches the
ORM, so each model is unit-tested over hand-written arrays independently of any
fixture. `apps.ai` has **no models and no migrations**.

### The failure boundary

Every service entry point is wrapped by `_decision_support`: `InsufficientData`
becomes `{"available": false, "reason": "INSUFFICIENT_DATA"}`, any other
exception is logged with a traceback and becomes `{"available": false,
"reason": "MODEL_ERROR"}`. The raw exception text never reaches the client and
the endpoint never returns 500 for a model failure.

The stronger guarantee is structural: **no business module imports `apps.ai`
or `ml`** (`test_no_business_module_imports_the_ai_layer` scans the sources).
Registration, evidence submission, verification, attendance, OD, achievement
and notification code paths make no AI call, so there is no transaction an AI
failure could roll back. `test_every_core_workflow_succeeds_while_every_model_is_broken`
patches all three models to raise and drives each workflow to success.

### Authorization

The same `AnalyticsScope` boundary analytics and reports use, applied **before**
any row is returned. Models are fitted on the identity-free, system-wide
feature matrix so a level means the same thing for every caller, and then only
rows inside the caller's scope are returned.

- Recommendations and engagement have **no student parameter at all** - the
  subject is always `request.user`, so there is no id to tamper with. Staff
  accounts get 403 on recommendations (a recommendation is personal to one
  student's history; no administrative workflow needs another person's).
- `?evidence=<id>` on anomalies is resolved against `scope.evidence()` first;
  an id outside the scope is a 404 before any model runs.
- Faculty receive the engagement distribution only, never per-student labels;
  HOD and Admin receive labels for students they are already authorized to see.
- A staff account with no department matches nothing (same null guard as
  Phases 5-7). Query parameters never widen scope.
- No response carries a password hash, token, evidence object reference, GPS
  coordinate or storage path, asserted by tests that scan the bodies.

### Features (`apps/ai/features.py`, `FEATURE_VERSION = features-v1`)

**Recommendation** - one-hot category (weight 1.0), department match (0.6),
live-registration popularity normalised to the current maximum (0.4), recency
of `event_date` within 90 days (0.3). History = participations plus live
registrations. Candidates = PUBLISHED events whose registration window is open
today, excluding **any** event the student already has a registration row for
(a cancelled registration can never be re-created because of the unique
`(student, event)` constraint, so recommending it would recommend the
impossible).

**Anomaly** - each feature is labelled with a temporal status and none is the
outcome of the record itself, so the model cannot learn "rejected records look
rejected":

| Feature | Status |
| --- | --- |
| `capture_count`, `version_count`, `max_venue_distance_m`, `mean_venue_distance_m`, `mean_gps_accuracy_m`, `mean_upload_delay_s`, `location_warning_ratio` | PRE-VERIFICATION (known at submission) |
| `prior_submissions`, `prior_rejection_ratio` | HISTORICAL (other records of the same student, decided **before** this record was created) |

Missing values are median-imputed inside the model. Signals are emitted only
when a feature exceeds a stated threshold (e.g. distance > 200 m **and** > 2x
the population median); a row whose features crossed nothing says so rather
than inventing a reason.

**Engagement** - `registrations, participations, verified, attendance_approved,
od_approved, official_achievements, category_diversity, recency_score`, built
from grouped `Count(filter=...)` queries (query-count tests assert no N+1).

### Model behaviour worth knowing

- **KNN** score = `1 / (1 + mean distance to the k nearest history events)`,
  in (0, 1]. It is a similarity, **not a probability**, and the response says so
  in `score_basis`. Cold start (no history) uses a documented deterministic
  ranking - `0.5*department + 0.3*popularity + 0.2*soon` - and is labelled
  `model: "cold_start"` so it can never be mistaken for a model output.
- **Isolation Forest** needs `MIN_SAMPLES = 5`; below that it is
  `INSUFFICIENT_DATA`. Levels are population-relative: HIGH = forest outlier
  **and** score >= 90th percentile; MEDIUM = either; else LOW. The thresholds
  and the rule are returned with every response.
- **K-Means** cluster ids are arbitrary. Labels come from ordering the
  inverse-transformed centroids by a documented weighted sum
  (`ENGAGEMENT_WEIGHTS`), so LOW/MODERATE/HIGH always mean what they say. K:
  0-1 students -> `INSUFFICIENT_DATA`; 2 -> K=2 (LOW/HIGH); 3+ -> K=3, capped at
  the number of distinct vectors; all-identical vectors -> one MODERATE group
  with an explanatory `note`.
- Everything is `random_state=42`; repeated calls over the same data return
  identical output, and the tests assert it.

### Limitations, stated honestly

- **There is no ground truth.** The system has no confirmed-fraud labels, so
  no precision, recall, accuracy or AUC is reported anywhere - a risk level is
  an isolation signal, not a detection rate. Recommendations have no
  click/registration feedback loop, so no relevance metric exists either.
- Populations are small; percentile thresholds on a handful of records are
  coarse, and a single unusual record shifts them. This is expected and the
  population size is returned with every response.
- Models are refitted per request over the current data (no persistence).
  Measured on the development Neon database this is hundreds of milliseconds,
  dominated by the round trips; it is not designed for tens of thousands of
  rows, and if that day comes the fix is caching the feature matrix, not
  changing the boundary.
- Recommendation reasons are limited to what the features encode - category,
  department, popularity, timing. The model does not know why a student chose
  an event.

### Audit

Reading a signal is not a business action and is **not** audited; only human
decisions are, exactly as before. No `AuditLog` action was added.

## Hardening and quality assurance (Phase 9)

Phase 9 added no feature. It read every app against the security rules above,
wrote a cross-app hardening suite, fixed what the suite found, and left the
codebase lint-clean.

### The cross-app suite (`backend/tests/`, 106 tests)

`tests/` is the integration-test directory `pytest.ini` already pointed at;
Phase 9 is the first phase to populate it. Each module is a matrix or a
scenario that spans apps rather than testing one:

| Module | What it proves |
| --- | --- |
| `test_authentication_security.py` | malformed/expired/tampered JWTs → 401; refresh-as-access and access-as-refresh refused; rotated and logged-out refresh tokens are dead; a deactivated account's tokens stop immediately; the role claim in a token is never trusted; no response carries a hash or token; login throttle fires on the 11th attempt; `ai` and `reports` throttle scopes fire |
| `test_authorization_matrix.py` | every collection endpoint × {anonymous, Student, Faculty, HOD, Admin} with the expected status written out as data; read-only resources reject writes for every role; lists contain only in-scope ids |
| `test_idor_matrix.py` | Student A2/B against every record of Student A → 404; department B staff against department A → 404; Faculty cannot perform HOD decisions (403); the one pinned deviation (registration-request review across departments is 403) is asserted so a change is deliberate |
| `test_input_hardening.py` | SQL-injection payloads in every text filter are inert literals; every numeric/date filter rejects garbage with 400, never 500; pagination and report-type paths are bounded |
| `test_mass_assignment.py` | protected fields (`status`, `created_by`, `department`, `reviewed_by`, `reviewed_at`, `recipient`, `read_at`, `is_active`, `is_superuser`, …) submitted on every writable endpoint are ignored or refused |
| `test_file_upload_security.py` | SVG/HTML/executable/zip bytes rejected whatever the Content-Type claims; the bytes decide the stored MIME; GIF/BMP refused; empty/truncated/oversized/tiny files refused; hostile filenames never reach the storage key; a polyglot JPEG is served only as `image/jpeg` with `nosniff`; `capture_role` is a closed choice |
| `test_timestamp_boundaries.py` | the event-date rule at 00:00:00 / 23:59:59 IST and the same instants expressed in UTC; the 5-minute future skew; server-owned timestamps cannot be supplied |
| `test_workflow_lifecycle.py` | Event → registration → participation → live capture → Faculty verification → attendance → OD → achievement → notifications → dashboard → analytics → report → AI → audit, through the API; every refused state transition |
| `test_transaction_safety.py` | a failing audit write rolls the decision back (attendance, OD, achievement, Faculty decision, HOD override, version open, registration, event lifecycle, participation open); a failing notification or AI model never does |
| `test_security_configuration.py` | hardening headers on every response; report downloads `no-store`; `MEDIA_URL` not served; storage paths never exposed; settings environment-driven; CORS an explicit allowlist; JWT rotation/blacklist on; no connection strings, private keys or JWTs anywhere in the repository; `.env` untracked |
| `test_performance_large_data.py` | 200 students / 40 events / 1 600 registrations / 600 participations+evidence / 1 500 notifications built in the **test** database; the query count of twenty endpoints and six report exports does not change when the data grows; AI stays available and scoped; every list stays paginated |

### Defects found and fixed

1. `GET /registrations/?event=<non-numeric>` raised `ValueError` inside the ORM → **500**. Now 400.
2. `GET /audit/` and `GET /activity/` with a malformed `date_from`/`date_to` raised Django `ValidationError` inside the ORM → **500**; a non-numeric `actor` was silently ignored. Now 400.
3. `EventSerializer.my_registration_status` issued one query per event for a student listing events (N+1). The list view now prefetches the caller's own registrations.
4. `GET /evidence/captures/<id>/image/` answered **403** for a capture outside the caller's scope, revealing that the id exists; every other resource answers 404. Now 404.
5. Several Phase 1–3 writes committed the business row and *then* wrote the audit row in a second implicit transaction, so an audit failure left a row with no trail: registration create/cancel, event create/update/publish/cancel, participation open, registration-request reject. Each is now one `transaction.atomic` block. (HOD approval and every Phase 4–8 service were already atomic.)
6. On-request model fitting and in-memory report rendering had only the generic 120/min user throttle. New scopes: `ai` 30/min, `reports` 20/min.
7. `SECURE_BROWSER_XSS_FILTER` — removed from Django in 4.0 — was still set; replaced by an explicit `SECURE_REFERRER_POLICY = 'same-origin'` (Django's default, made visible).
8. `flake8` (now configured in `.flake8`, max line length 120) reported 52 findings: 22 unused imports, 27 long lines, 3 layout. All fixed; the project is lint-clean.

No application defect was found in authentication, authorization scope, the
live-capture rules, evidence privacy, notification scoping, analytics/report
scoping or the AI boundary: the new matrices confirmed the Phase 1–8
behaviour.

### Reviewed and deliberately unchanged

- Registration-request approve/reject by an HOD of another department answers 403 (the request's existence is not sensitive between HODs). Pinned by a test.
- The Phase 4 `department_id == user.department_id` comparison without a null guard in `apps.verification` / `apps.events` / `apps.participation` permissions. Every API path that creates a Faculty or HOD requires a department, so the NULL case cannot arise through the API; it remains flagged for the user's decision as in Phases 5–8.
- `RegistrationStatusView` is public by design (an applicant cannot log in) and reveals whether a username has a pending request; it sits behind the 10/min `auth` throttle.
- JWTs live in `localStorage` (Phase 1 decision); the access token is 30 minutes and every refresh rotates and blacklists.
- Test-suite warnings (12): 11 × `RemovedInDjango60Warning` from DRF's `drf_format_suffix` converter registration and 1 × `DeprecationWarning` from reportlab's `ast.NameConstant` probe — both third-party, neither actionable in this codebase, neither suppressed.

### Results

- `pytest -q`: **722 passed, 6 failed (all six Neon connection drops, re-run in isolation: 14 passed), 12 warnings in 6358.65s (1:45:58) — i.e. 728/728 green**
- `python manage.py check` / `check --deploy` (DEBUG=False): no issues · `makemigrations --check`: no changes · `migrate --plan`: no planned operations · `spectacular --fail-on-warn`: clean (92 operations) · `flake8`: 0
- Frontend: `tsc` clean · `ng test`: **301 SUCCESS (301 of 301)** · `ng build`: clean, 0 warnings, initial bundle 549.53 kB
- `npm audit --omit=dev`: 0 vulnerabilities · `pip check`: no broken requirements. No dependency was changed.
- Live lifecycle against the dev server + real Neon (`e2e_phase9_http.py`): all checks passed. Browser E2E: not performed (tooling unavailable).

---

## Production, deployment and documentation (Phase 10)

No new business features. Phase 10 turns a working application into a
deployable, documented one, and fixes the production-configuration defects the
audit found.

### Production configuration — fail fast, never fail quietly

`config/settings.py` now reads `DEBUG` first and treats every setting that would
be a security defect in production as a startup error rather than a default:

| With `DJANGO_DEBUG=False` | Previously | Now |
|---|---|---|
| `DJANGO_SECRET_KEY` absent | Silently used `django-insecure-dev-key-change-me` | `ImproperlyConfigured` at import |
| `DJANGO_ALLOWED_HOSTS` empty or `*` | Accepted | `ImproperlyConfigured` |
| `CORS_ALLOWED_ORIGINS` empty or `*` | Accepted | `ImproperlyConfigured` |
| `CSRF_TRUSTED_ORIGINS` containing `*` | Not configured at all | `ImproperlyConfigured` |

A server that refuses to start is a far better outcome than one running with a
known secret key or a wildcard host.

### Database — the SQLite fallback is gone

`DATABASE_URL` is now **required in every environment**. A blank value raises
`ImproperlyConfigured` naming `.env.example`, instead of silently switching to a
local SQLite file.

The fallback was a setup convenience that had outlived its purpose, and it was a
real hazard: migrations, constraints and transaction semantics on SQLite are not
those of PostgreSQL, so a developer could have a green suite against a database
the application never runs on. `backend/db.sqlite3` was deleted; the `.gitignore`
pattern stays so a stale file can never be committed.

### Static files

WhiteNoise serves Django's own static assets (admin, DRF browsable API, Swagger
UI) from the WSGI process, so the reverse proxy needs no static rule at all.

- `CompressedManifestStaticFilesStorage` is installed **only** when `DEBUG` is
  off — the manifest exists only after `collectstatic`, and referencing an
  uncollected file would otherwise break local development.
- The middleware is likewise added only outside `DEBUG`: `runserver` already
  serves static files, and WhiteNoise would otherwise warn on every request
  about a `staticfiles/` directory that does not yet exist.
- Verified: `collectstatic` copies 163 files and post-processes 469, and the
  Django admin renders correctly with `DEBUG=False`.

### HTTPS behind a proxy

`SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` is set outside
`DEBUG`, gated behind `DJANGO_TRUST_PROXY_SSL_HEADER` so a deployment that
terminates TLS in the app process can turn it off. Without it,
`SECURE_SSL_REDIRECT` behind nginx is an infinite redirect.

Trusting that header is only safe when the proxy *sets* it rather than passing a
client-supplied one through, so `deploy/nginx.conf.sample` uses
`proxy_set_header X-Forwarded-Proto $scheme` and says why in a comment.

Also made explicit: `SECURE_CROSS_ORIGIN_OPENER_POLICY`,
`SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`, `CSRF_COOKIE_SAMESITE`.

### Logging

Three separated streams, all on stdout by default so a process supervisor owns
rotation:

| Logger | Carries |
|--------|---------|
| root | Application logs |
| `django.security` + `apps.security` | Authentication/authorization events: ids, usernames, roles, action names |
| `django.request` | Unhandled view exceptions, traceback **server-side only** |

`DJANGO_LOG_TO_FILE=True` additionally writes `application.log`, `security.log`
and `error.log` into `DJANGO_LOG_DIR`, rotating at 5 MB x 5.

Passwords, JWTs, refresh tokens, `Authorization` headers, the secret key and the
database password are never logged. `deploy/gunicorn.conf.py`'s access-log
format deliberately omits headers and bodies for the same reason.

### Health and readiness

`config/views.py` now distinguishes the two probes, which previously shared one
endpoint:

| Endpoint | Behaviour | For |
|----------|-----------|-----|
| `GET /api/v1/health/` | **Always 200** while the process serves; reports `database` as a field | Liveness: a transient database blip must not restart a healthy process |
| `GET /api/v1/health/ready/` | **200** when the database answers, **503** when it does not | Readiness: a proxy stops routing to an instance that cannot serve |

Neither exposes settings, credentials or a traceback; a connection error's text
(which can name the host and user of the connection string) is logged
server-side and never returned. Four new tests pin this, including one asserting
that neither response body contains the secret key, the database password or the
database host.

### Demo / seed data

`python manage.py seed_demo_data [--reset]` builds a full lifecycle dataset: a
college, two departments, an Admin, two HODs, two Faculty, five students, five
events (including one happening today and one Admin-created event with no
department), registrations including a cancelled one, and participations with
evidence in **every** reviewable state — verified, rejected, awaiting review and
HOD-overridden — plus attendance, OD, achievements and unread notifications.

Two safety properties:

- It **refuses to run when `DEBUG` is off**, with no override flag. Its accounts
  share a published password (`DemoPass123!`), so letting it near production
  would be handing out credentials.
- Every account is prefixed `demo_` and every record hangs off one, so `--reset`
  removes exactly what it created and nothing else.

Evidence is written directly against the models rather than through the API,
because the API correctly refuses a capture whose event date is not today and
the demo needs evidence on a past event too. The rows it writes are the rows the
API would have produced.

### Deployment configuration

`deploy/` holds the three files a production host needs:

- `gunicorn.conf.py` — loopback bind, `gthread` workers, timeouts sized for the
  two genuinely slow paths (report rendering, on-request model fitting), worker
  recycling, stdout logging, everything overridable by environment variable. It
  carries the warning that concurrent database connections are roughly
  `workers x threads` and must be checked against the Neon limit.
- `nginx.conf.sample` — TLS termination, HTTP to HTTPS with ACME left reachable,
  API/admin/static forwarding, SPA `try_files` fallback, `client_max_body_size`
  above the capture limit so an over-size upload gets Django's clear 400 rather
  than nginx's opaque 413, immutable caching for hashed assets and `no-store`
  for `index.html` — and **no `/media/` block**, with a comment saying never to
  add one.
- `ssepams.service` — a systemd unit with `EnvironmentFile` for secrets and
  filesystem hardening that leaves only `media/` writable.

Docker is deliberately absent. It was not present before this phase, the
deployment is a single unit, and adding it would be infrastructure the workload
does not justify.

### Defects found and fixed in this phase

1. **`SECRET_KEY` fell back to a development value in production.** `DEBUG=False`
   with no `DJANGO_SECRET_KEY` started successfully on the insecure default,
   making every issued token forgeable by anyone who had read the repository.
   Now a startup failure.
2. **`ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS` accepted a wildcard in
   production.** Now a startup failure.
3. **`CSRF_TRUSTED_ORIGINS` was never configured**, so the Django admin behind
   HTTPS on a different host than the API would have rejected every form post.
   Now environment-driven, defaulting to the CORS allowlist.
4. **`SECURE_SSL_REDIRECT` behind a proxy was an infinite redirect loop** — no
   `SECURE_PROXY_SSL_HEADER` was set.
5. **No production static file handling at all.** With `DEBUG=False` Django
   serves no static files, so the admin and Swagger UI would have been unstyled
   and partly broken on any real deployment. WhiteNoise now handles it.
6. **`apps/participation/storage.py` documented the wrong retrieval endpoint.**
   It named `GET /api/v1/participations/captures/{id}/image/`, which has not
   existed since Phase 4 moved capture retrieval to
   `GET /api/v1/evidence/captures/{id}/image/`: a security-critical comment
   pointing at code that is not there.
7. **Private evidence images were served with no cache directive.**
   `GET /api/v1/evidence/captures/{id}/image/` returned a bare `FileResponse`,
   so a browser was free to keep a student's participation photograph in its
   disk cache — still readable on a shared lab machine after logout. The
   report-download path has set `no-store` since Phase 7; the image path, which
   carries at least as sensitive data, had not. Fixed, and pinned by a new
   `test_evidence_image_is_never_cacheable`.
8. **The SQLite fallback** (above) — a correctness hazard rather than a bug.
9. **`.env.example` documented that removed fallback** and was missing every
   capture-threshold and HTTPS variable. Rewritten with all of them.

### Verification

See `docs/testing/test-results.md` for the full Phase 10 run, with the exact
commands and the classification of every failure.

---

## Admin user management and final audit pass

No architectural change. This pass closed a gap found during real-world manual
testing, then audited the rest of the project for the same class of problem.

### The gap

The Admin dashboard showed **Total Users** and **Active Users**, but both cards
linked to `/admin` — a page that shows neither count. There was no Admin user
management API at all: `/api/v1/users/` exposed only `me/`,
`me/password/`, `registration-requests/` and `provision-hod/`. An Admin could
create an HOD and approve a registration request, but could not list accounts,
correct an email, move someone between departments, deactivate a departed
student, or reset a forgotten password without dropping to the Django admin.

### Backend

Two new modules under `apps/accounts/`, kept separate from `views.py` and
`serializers.py` because they are the only place in the project where one user
may change another user's account, and that deserves to be reviewable as a unit:

| Module | Contents |
|--------|----------|
| `admin_serializers.py` | List/detail/update/password/stats serializers |
| `admin_views.py` | The six endpoints, all `IsAdminRole` |

| Method | Path | Purpose |
|--------|------|---------|
| GET | `users/` | Paginated list; `search`, `role`, `department`, `status`, `ordering` |
| GET | `users/stats/` | `{total, active, inactive, by_role}` |
| GET | `users/{id}/` | Detail, including the registration-request history |
| PATCH | `users/{id}/` | `email`, `first_name`, `last_name`, `role`, `department`, `is_active` |
| POST | `users/{id}/activate/` | |
| POST | `users/{id}/deactivate/` | |
| POST | `users/{id}/reset-password/` | `set_password()` + revoke the target's refresh tokens |

**Route ordering is not load-bearing.** The detail routes key on `<int:pk>`, so
they cannot shadow `me/`, `registration-requests/` or `provision-hod/` however
the list is reordered later. A `<str:pk>` would have made the ordering fragile;
`resolve()` for all six paths is asserted in the test suite's URL checks.

**Invariants enforced before the database has to.** `AdminUserUpdateSerializer`
is used by the activate/deactivate views as well as by `PATCH`, so there is one
copy of each rule rather than two that can drift:

- Student/Faculty/HOD must have a department.
- One active HOD per department — refused with a `400` naming the incumbent
  rather than an `IntegrityError` surfacing as a `500`. The partial unique index
  on `User` remains as the backstop.
- The system always keeps a usable Admin: the last active one cannot be demoted
  or deactivated.
- An Admin cannot deactivate their own account.
- A Django superuser's role cannot be changed, because `User.save()` forces it
  back to `ADMIN` — accepting anything else would be a lie.

**Not writable, deliberately:** `username` (the audit trail refers to accounts by
name, so renaming would orphan history), `is_staff` and `is_superuser`
(Django-level privileges belonging to `createsuperuser`), `date_joined`,
`last_login`. Sent values are ignored, not honoured.

**Concurrency.** Every mutation runs in `transaction.atomic()` and re-reads the
row with `select_for_update()`, so two Admins cannot both pass the "one active
HOD" check and then both write.

**Password reset** validates with Django's configured validators, hashes with
`set_password()`, and **blacklists the target's outstanding refresh tokens** — a
reset exists to take an account back under control, so a session opened before
it must not survive it. No password material is stored, logged, echoed or
returned; the response carries only a confirmation and the number of sessions
ended.

**Audit.** `ADMIN_USER_UPDATED` (with the field names and old → new values),
`ADMIN_USER_ACTIVATED`, `ADMIN_USER_DEACTIVATED`, `ADMIN_PASSWORD_RESET`. A
no-op `PATCH` writes no entry — an audit trail full of "changed nothing" is
harder to read, not safer.

**Query shape.** The list uses `select_related('department')`, so its query count
does not grow with the number of accounts; a test asserts the count is unchanged
after adding a dozen users rather than pinning a literal, so it fails on an N+1
and not on unrelated fixed overhead.

### Dashboard card routes

The reported defect was two cards. The audit found four, because a card whose
route leads somewhere that does not show that count is the same bug regardless
of which card it is:

| Card | Was | Now | Why |
|------|-----|-----|-----|
| Total Users | `/admin` | `/admin/users` | The page that shows the count |
| Active Users | `/admin` | `/admin/users` + `?status=active` | Lands already filtered |
| Participations | `/admin/attendance` | `/analytics` | **Participation is not attendance.** Sending an Admin to the attendance screen for a participation count contradicts the distinction the whole system is built on |
| Pending Verification | `/admin/attendance` | `/analytics` | Same: verification is not attendance |

`Departments → /admin` was checked and left alone — department management and
HOD provisioning genuinely live on that page.

**A query string cannot live inside `route`.** Angular's `routerLink` given a
bare string treats the whole value as one path segment, so
`"/admin/users?status=active"` would be encoded to `%3F` and navigate nowhere
useful. The card payload therefore grew an explicit `query` dict which the
template binds to `[queryParams]`, and a frontend spec asserts the rendered
`href` contains a real `?` and no `%3F`.

### Frontend

| Path | |
|------|---|
| `core/models/admin-user.model.ts` | New. Separate from `User` so the self model never grows an `is_superuser` flag some component then reads as authorization |
| `core/services/user-admin.service.ts` | Extended with list/stats/get/update/activate/deactivate/resetPassword |
| `features/admin/users/user-management.component.*` | New page at `/admin/users` |
| `features/admin/admin-shell.component.html` | "Users" added to the Admin navigation |
| `features/dashboard/dashboard.component.html` | Binds `[queryParams]` |

Filtering, searching and paging are all server-side; the component never holds
the full list and never filters in the browser. Filter state is mirrored into
the URL, which is what makes the dashboard deep link work and also makes a
filtered view bookmarkable.

The `queryParamMap` subscription is torn down with `takeUntilDestroyed` —
`ActivatedRoute` observables do not complete on destroy, so without it every
visit to the page would leave a live subscription behind.

### Tests added

- `apps/accounts/tests/test_admin_user_management.py` — 43 tests: authorization
  for all four roles, search/filter/pagination, every edit invariant, activation,
  password reset (including that the response and the audit entry contain no
  password, that the stored value is hashed, and that the target's refresh
  tokens stop working), and the query-count budget.
- `features/admin/users/user-management.component.spec.ts` — 14 specs.
- One dashboard spec pinning the `?status=active` deep link.
