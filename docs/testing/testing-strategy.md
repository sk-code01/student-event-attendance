# Testing Strategy

## What is being defended

Three claims, in priority order:

1. **Authorization holds.** No role, department or ownership boundary can be
   crossed, by any route, including by guessing identifiers.
2. **The business rules hold.** Registration ≠ participation ≠ attendance
   approval ≠ achievement; a capture is valid only on the event date; a
   verification history is append-only.
3. **Nothing regressed.** Every phase's behaviour is still true after the next
   phase's changes.

Everything below exists to defend one of those.

---

## Levels

| Level | Where | What it covers |
|-------|-------|----------------|
| Model / unit | `apps/*/tests/test_models.py`, `apps/ai/tests/test_ml_units.py` | Database constraints, field validation, pure ML functions over numpy arrays |
| API / integration | `apps/*/tests/` | Real HTTP requests through DRF with a real JWT against a real PostgreSQL database |
| Cross-app security | `backend/tests/` | Authorization matrix, IDOR matrix, mass assignment, upload security, input hardening |
| Workflow | `backend/tests/test_workflow_lifecycle.py` | The whole chain end to end |
| Performance | `apps/analytics/tests/test_query_budget.py`, `backend/tests/test_performance_large_data.py` | Asserted query counts, so an N+1 fails a test |
| Frontend unit | `frontend/src/**/*.spec.ts` | Services, guards, the interceptor, components, camera/GPS/queue behaviour |

**Tests run against real PostgreSQL (Neon), never SQLite.** Constraints,
transaction semantics and type behaviour are part of what is being tested, and a
different engine would test something else.

**API tests drive the API.** Authorization tests obtain a genuine token via
`POST /api/v1/auth/token/` and make real requests. A test that called a service
function directly would prove the service works, not that the endpoint is
protected.

---

## Fixtures

`backend/tests/helpers.py` builds a two-department "universe": a college, an
Admin, and in each department an HOD, a Faculty, a Student, three events in
different states, a verified participation with evidence and a verification
trail, an attendance, an OD request, an achievement and a notification — plus a
second student in department A who owns nothing.

That shape is what makes an authorization test readable: "student B's token
against student A's evidence" is one line, and every cross-boundary pair exists.

Fixtures are built through the **existing per-app helpers**, so they cannot
drift from what the applications consider a valid record.

---

## Backend coverage by area

| Area | Files | Focus |
|------|-------|-------|
| Accounts | 8 | Auth, JWT regression, logout, password change, role permissions, self-registration and its approval workflow, **Admin user management** (authorization for all four roles, search/filter/pagination, every edit invariant, activation, password reset, query budget) |
| Events | 4 | Creation rules, lifecycle (draft→published→cancelled), per-role visibility, model constraints |
| Registrations | 4 | Creation, window enforcement, cancellation, access scope, duplicate race condition |
| Participation | 5 | Eligibility, creation, models, IDOR, race condition on concurrent creation |
| Verification | 8 | Capture upload validation, submit rules, Faculty decisions, HOD override, resubmission versioning, concurrency, IDOR |
| Attendance | 4 | Workflow, eligibility from the effective decision, concurrency, IDOR |
| OD | 4 | Workflow, **independence from attendance**, concurrency, IDOR |
| Achievements | 3 | Workflow and status transitions, concurrency, IDOR |
| Notifications | 3 | Service behaviour and dedupe, API scope, integration with each workflow transition |
| Dashboard | 1 | Per-role aggregation |
| Audit | 1 | Append-only, read scope |
| Analytics | 4 | Authorization, correctness (including zero denominators), trends, **query budget** |
| Reports | 1 | All 12 types × 3 formats, scope, filenames, headers, empty reports |
| AI | 5 | Recommendations, anomalies, engagement, ML units, **security and safety** |
| Colleges / Departments | 4 | Reference-data models and API, plus **reference-data pagination** (a dropdown must be able to fetch every row, and the page size must stay capped) |
| Cross-app | 11 | See [`security-testing.md`](security-testing.md) |

**70 backend test files.**

### Things that are specifically pinned

- **Race conditions.** Concurrent duplicate registration, concurrent
  participation creation, and concurrent approval on attendance, OD,
  achievements and verification.
- **Transaction safety.** A notification failure cannot roll back the business
  transaction that triggered it.
- **Timestamp boundaries.** The event-date rule at midnight, clock skew, and a
  delayed offline sync of a same-day capture.
- **Query budget.** Concrete query counts on the analytics and list endpoints.
- **AI safety.** No business service imports `apps.ai`; every AI failure is
  contained; no AI endpoint widens scope.

---

## Frontend coverage

**52 spec files, 317 specs.** Run headless in Chrome via Karma + Jasmine.

| Area | Focus |
|------|-------|
| `auth.service` | Token storage, session lifecycle, role exposure |
| `auth.interceptor` | Header attachment, single shared in-flight refresh, replay after refresh, redirect on failure |
| `auth.guard` / `role.guard` | Route protection (UX layer — the API is tested separately) |
| `camera.service` | Secure-context check, `getUserMedia` error mapping, frame capture, track release |
| `geolocation.service` | Permission, unavailable, timeout error mapping; no fabricated coordinates |
| `offline-capture-queue.service` | Enqueue, user scoping, sync on reconnect, failure recording, no token stored |
| Feature services | Every API service's request shape and response mapping, including that a dropdown request asks for every row |
| `user-management` | Server-side filtering, the query-string deep link, refused-action messages, and that no password is ever rendered |
| Components | Rendering per role and per state |

Browser APIs are mocked **in tests only**. `CameraService` and
`GeolocationService` have no mock path in production code — an unsupported
browser produces a typed error, never a fake value.

---

## What is not covered

Stated plainly rather than implied:

- **No browser end-to-end suite.** There is no Playwright, Cypress or Selenium
  suite in this repository. The camera and GPS workflow is covered by unit tests
  with mocked browser APIs plus backend API tests, and was exercised manually in
  a real browser. See [`test-results.md`](test-results.md).
- **No load or stress testing.** Query-count budgets bound the per-request cost;
  concurrent-user throughput has not been measured.
- **No AI accuracy metrics.** There is no ground-truth labelled dataset, so no
  precision, recall or accuracy can honestly be quoted. The AI tests are
  behavioural: determinism, cold start, small-data policy, scope isolation,
  failure containment.
- **No penetration test.** The security suites cover the classes of flaw the
  team identified; they are not a substitute for an independent assessment.

---

## Running the tests

```bash
# Backend — from backend/, with the virtualenv active
pytest                       # everything
pytest -q                    # quiet
pytest apps/verification     # one app
pytest --create-db           # rebuild the test database after a model change

# Backend checks
python manage.py check
python manage.py check --deploy          # with production environment variables
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python -m flake8 .

# Frontend — from frontend/
npm test -- --watch=false --browsers=ChromeHeadless
npx tsc -p tsconfig.app.json --noEmit
npm run build
npm audit --omit=dev
```

**A note on Neon.** The full backend suite runs against a remote database, so it
takes considerably longer than a local one would and is exposed to Neon's pooler
behaviour. `pytest.ini` sets `--reuse-db` because the pooler can hold a session
open and block `DROP DATABASE` at teardown.

If a test fails during a long run, **classify it before reporting it**: re-run it
in isolation, and distinguish a genuine regression from a transient connection
error. A suite is never reported as green while a failure is unexplained.
