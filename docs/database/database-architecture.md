# Database Architecture

## Engine

**PostgreSQL, hosted on NeonDB.** In development as well as in production.

There is deliberately **no SQLite fallback**. A missing `DATABASE_URL` is a
configuration error that stops the application at import time with an explicit
message. Falling back to a different engine would let migrations, constraints,
transaction semantics and query behaviour diverge quietly between a developer's
machine and production — the class of bug that only appears after deployment.

## Configuration

One environment variable carries the whole connection, exactly as Neon's
dashboard provides it:

```
DATABASE_URL=postgresql://user:password@ep-xxxx.<region>.aws.neon.tech/dbname?sslmode=require
```

`config/settings.py` parses it with `dj-database-url`:

```python
DATABASES = {
    'default': dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=config('DB_CONN_MAX_AGE', default=60, cast=int),
        ssl_require=True,
    )
}
```

**`ssl_require=True` is unconditional.** Neon only accepts TLS, and this also
stops a copy-pasted URL that lost its `?sslmode=require` from silently
downgrading the connection.

**`conn_max_age` (default 60 s)** keeps a connection alive between requests
instead of reconnecting on each one — worth a lot against a remote database.
Keep it modest: Neon's pooler counts idle sessions, and a long-lived pool
multiplied by Gunicorn workers can exhaust the connection allowance. Size it as
*workers × threads ≤ your Neon connection limit*, and prefer Neon's **pooled**
endpoint (the hostname containing `-pooler`) for the application.

**Driver:** `psycopg[binary]` 3.2.

## Time

| Setting | Value | Consequence |
|---------|-------|-------------|
| `USE_TZ` | `True` | Every `DateTimeField` is stored in UTC |
| `TIME_ZONE` | `APP_TIMEZONE`, default `Asia/Kolkata` | The institution's calendar |

Every *business day* decision — is the registration window open, is today the
event date, is an achievement date in the future — is taken with
`django.utils.timezone.localdate()`, which converts to `APP_TIMEZONE`. The
browser's local date is never trusted for a rule, and the server's UTC date is
never used directly. This is what stops the browser, the server and the stored
timestamp from disagreeing about which calendar day it is.

`Event.event_date`, `registration_start_date`, `registration_end_date` and
`achievement_date` are plain `DateField`s — a calendar day, not an instant.

## Migrations

17 migration files across 12 apps, all of them deterministic and committed.

```bash
python manage.py makemigrations --check --dry-run   # fails if a model change is unmigrated
python manage.py migrate --plan                     # shows what would run
python manage.py migrate                            # applies
```

Two migrations are worth knowing about, because they encode a real schema
evolution rather than a fresh table:

| Migration | What it does |
|-----------|--------------|
| `verification/0002_migrate_participation_captures` | Data migration moving Phase 3's `ParticipationCapture` rows into the Phase 4 `EvidenceVersion`/`EvidenceCapture` model |
| `participation/0003_delete_participationcapture` | Drops the old table **after** the data migration |

`apps/participation/models.py` still defines `MIME_EXTENSIONS` and
`capture_upload_path` even though `ParticipationCapture` is gone. That is not
dead code: `FileField.upload_to` is frozen in migration history as a
`module.attribute` reference, so removing the name would break migration
replay. The module comment says so.

## Constraints — the last line of defence

Business invariants are enforced by the database, not only by Python. A bug in a
view, a race between two requests, or a future refactor cannot violate them.

| Invariant | Mechanism |
|-----------|-----------|
| A department has at most one active HOD | `UniqueConstraint` on `accounts.User`, conditional on role and `is_active` |
| One registration per (student, event) | `UniqueConstraint` on `Registration` |
| One participation per registration | `OneToOneField` |
| One evidence per participation | `OneToOneField` |
| Evidence version numbers are unique per evidence | `UniqueConstraint(evidence, version_number)` |
| Exactly one `PRIMARY` capture per version | Conditional `UniqueConstraint` on `(evidence_version, capture_role)` |
| One attendance per participation | `OneToOneField` |
| One OD request per participation | `OneToOneField` |
| Notification dedupe | `UniqueConstraint` on the dedupe key |
| Rejection/override rows keep a reason | `CheckConstraint` |

## Deletion policy

Workflow rows use `on_delete=models.PROTECT`, not `CASCADE`. An event with
registrations, a participation with evidence, or a user who has reviewed
something cannot be deleted out from under the audit trail. Rows that are
genuinely owned by their parent — `EvidenceVersion` under `Evidence`,
`EvidenceCapture` under `EvidenceVersion` — cascade, because they have no
independent meaning.

`Evidence.current_version` is `SET_NULL` so the pointer can be detached without
taking the history with it.

## Transactions

Any multi-step state change runs inside `transaction.atomic()` in its app's
service layer. Two consequences that are tested rather than assumed:

- **A partially applied workflow transition is impossible.** If the notification
  emitted by a verification decision fails, that failure is contained and cannot
  roll back the decision — `backend/tests/test_transaction_safety.py`.
- **Concurrent approvals do not double-apply.** Approval paths select the row
  for update before transitioning — `apps/achievements/tests/test_concurrency.py`.

## Query performance

Every list endpoint uses `select_related` / `prefetch_related` for the
relationships its serializer walks, so response cost does not grow with page
size. Analytics aggregates in the database — `AnalyticsScope` hands out an
already-filtered queryset and every metric is a grouped query, never a
per-row loop with a query inside.

`apps/analytics/tests/test_query_budget.py` and
`backend/tests/test_performance_large_data.py` assert concrete query counts, so
an N+1 reintroduced by a future change fails a test rather than being noticed in
production.

## Operational notes

**Test database.** `pytest.ini` sets `--reuse-db`. Neon's pooler can hold a
server-side session open after the client disconnects, which blocks
`DROP DATABASE` during teardown; reusing the test database avoids create/drop
entirely. After changing a model, run `pytest --create-db` once to rebuild it.

**Backups.** Neon provides point-in-time restore on its own schedule; configure
the retention your institution requires in the Neon console. The application
performs no backups of its own.

**Evidence images are not in the database.** They are files under `MEDIA_ROOT`
(see [`../architecture/live-capture-architecture.md`](../architecture/live-capture-architecture.md#storage-and-retrieval)),
referenced by an object key. A database backup alone does **not** back up
evidence — the media directory must be backed up separately. This is stated in
the production checklist.
