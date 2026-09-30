# Final Project Handoff

**SEAMS-AI — Student Event & Attendance Management System with AI**

Phase 10 (final). This document states what was built, what was verified, and
what was deliberately not built. Where a number appears it is a measured result,
not an estimate; where something is absent it is named as absent rather than
implied.

---

## Project

A modular-monolith web application that records which students actually took
part in which college events, verified by a live camera capture with a GPS fix
taken on the event date, and carries that evidence through faculty verification,
HOD approval, attendance and on-duty records, achievements, analytics and
reporting.

The design is governed by one distinction:

> **Registration ≠ Participation ≠ Attendance Approval ≠ Achievement.**
> Registering is intent. Participation is evidence. Attendance approval is a
> decision. An achievement is a separate record. None produces the next
> automatically — each requires a deliberate act by the authorized person, and
> the schema is shaped so that skipping one is impossible rather than merely
> discouraged.

---

## Architecture

One Django project, one database, one deployable unit, divided internally into
apps that own their models, permissions, services and tests. Angular is a
separate SPA that talks to it only over `/api/v1/`.

```
Browser (Angular 20 SPA: camera, geolocation, IndexedDB offline queue)
   │ HTTPS, Bearer JWT
nginx (TLS termination, request limits, SPA routing)
   │ HTTP loopback
Gunicorn → Django 5.1 + DRF   ·   ml/ (scikit-learn)   ·   media/ (private evidence)
   │ TLS, psycopg 3
PostgreSQL (NeonDB)
```

No message broker, no task queue, no cache server, no container orchestrator, no
GraphQL, no WebSockets. The workflow is a single transactional chain, and
splitting it across services would replace database transactions with
distributed coordination for no benefit.

Detail: [`architecture/system-architecture.md`](architecture/system-architecture.md).

---

## Technology Stack

| Layer | Stack |
|-------|-------|
| Frontend | Angular 20.3 (standalone components, signals), RxJS 7.8, Bootstrap 5.3, TypeScript 5.9 |
| Backend | Django 5.1.5, DRF 3.15.2, simplejwt 5.4, drf-spectacular, django-filter, python-decouple |
| Database | PostgreSQL on NeonDB, `psycopg` 3.2.4, `dj-database-url`. **No SQLite fallback in any environment** |
| Files | Pillow (validation), private `FileSystemStorage` |
| Reports | stdlib `csv`, `openpyxl`, `reportlab` |
| ML | scikit-learn 1.6.1, pandas 2.2.3, numpy 2.2.2 |
| Production | Gunicorn, WhiteNoise, nginx, systemd |
| Testing | pytest, pytest-django, factory-boy, pypdf, flake8; Karma + Jasmine headless Chrome |

---

## Implemented Modules

**16 Django apps**, each owning its models, serializers, permissions, services
and tests:

`accounts` · `departments` · `colleges` · `events` · `registrations` ·
`participation` · `verification` · `attendance` · `od` · `achievements` ·
`notifications` · `dashboard` · `audit` · `analytics` · `reports` · `ai`

**Angular feature areas**: auth, events, participation (live capture, history),
faculty (verification queue and detail, requests, achievements), hod
(verification override, attendance, od, achievements), student (attendance, od,
achievements), admin (colleges, oversight), analytics, reports, audit,
notifications, ai (recommendations, anomalies, engagement, dashboard panel).

**100 API operations** under `/api/v1/`, all described by a generated OpenAPI
schema at `/api/v1/schema/` with a Swagger UI at `/api/v1/docs/`.

---

## Security

| Area | Measure |
|------|---------|
| Authentication | JWT — 30-minute access, 7-day refresh, rotation with blacklist on use, server-side logout |
| Role claim | **Never the authorization decision.** The database row is read on every request |
| Authorization | Permission classes + role-scoped querysets applied *before* aggregation + object-level checks |
| IDOR | Out-of-scope records return `404`, never `403`, so an id cannot probe for existence. Two deliberate deviations are pinned by tests |
| Mass assignment | Every server-set field is read-only and silently ignored when posted |
| Deactivation | `is_active = False` stops login, existing access tokens and refresh immediately |
| Admin user management | Admin-only; `username`/`is_staff`/`is_superuser` are not writable; the last active Admin cannot be demoted or deactivated; one active HOD per department is enforced before the database has to; an Admin-initiated password reset revokes the target's refresh tokens and returns no password material |
| Uploads | Content type from the decoded bytes (not the header); size and dimension bounds; SHA-256; **server-generated object keys**, so a client filename never touches a storage path |
| Evidence privacy | `MEDIA_URL` never routed, storage `base_url=None`, retrieval only via an authenticated, object-authorized endpoint, streamed `no-store` so no browser cache retains it |
| Input | NUL bytes rejected before any view; parameterised ORM queries; hardened pagination; closed report registry with no path built from user input |
| Transport | HTTPS required; HSTS, secure cookies, SSL redirect and proxy-header handling automatic when `DEBUG=False` |
| Headers | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin` on every response |
| CORS | Explicit allowlist; the application **refuses to start** with a wildcard in production |
| Configuration | A development secret key, a wildcard host or a wildcard origin with `DEBUG=False` is a startup failure, not a warning |
| Throttling | Separate scopes: `anon` 20/min, `user` 120/min, `auth` 10/min, `ai` 30/min, `reports` 20/min |
| Logging | Passwords, JWTs, refresh tokens, `Authorization` headers, the secret key and the database password are never logged |
| Audit | Append-only, including `REPORT_GENERATED` for every export |
| Secret hygiene | A test walks the whole repository for connection strings, AWS keys, PEM blocks and JWT-shaped strings, and asserts `backend/.env` is untracked. It reports file and line only, never the value |

---

## Live Participation Capture

The feature that makes participation verifiable rather than claimed. All twenty
finalized rules are implemented; the full matrix of where each is enforced is in
[`architecture/live-capture-architecture.md`](architecture/live-capture-architecture.md).

The ones that carry the most weight:

- Valid **only on the event's exact date**, compared against the capture's own
  **device timestamp**, so a delayed offline sync of a same-day capture still
  counts and a wrong-day capture never does — however late or early it is
  uploaded.
- **Camera frames only.** `getUserMedia` plus a canvas frame grab; there is no
  file input anywhere in the UI, so gallery upload is not possible.
- **GPS mandatory.** A missing accuracy value is treated as *unknown* and blocks
  submission; it is never treated as perfect.
- **Venue distance warns, never blocks.**
- **Unlimited retakes** before submission.
- **Offline capture queues** in IndexedDB, syncs on reconnect, stores **no
  token**, and is scoped to the authenticated user.
- **Both timestamps kept** — the device's, and the server's (the only one the
  server vouches for).
- **HTTPS is mandatory**, because browsers expose camera and geolocation only in
  a secure context.
- **No QR attendance. No face recognition.**

---

## Evidence Verification

- Evidence is **versioned**. A resubmission creates a new version; nothing is
  ever edited in place.
- Version numbers are **server-controlled** and unique per evidence (database
  constraint).
- **Exactly one PRIMARY capture** per version (database constraint); additional
  captures unbounded.
- The verification trail is **append-only**. An HOD override is a new row with
  `is_hod_override = True`; the Faculty decision it supersedes is never
  overwritten or deleted, and both remain visible with both reasons.
- The **effective decision** — the override if one exists, otherwise the Faculty
  decision — is *derived*, never stored, and is what every downstream workflow
  reads.
- Rejection, resubmission and override **reasons are mandatory** and are shown
  to the student verbatim.
- Cross-student and cross-department access returns `404`.

---

## Attendance and OD

Two **independent** workflows over the same shape. Faculty request; HOD (or
Admin) approves. Faculty cannot approve — including records they created
themselves.

Approving attendance says nothing about OD and vice versa; neither is derived
from the other, and OD is not modelled as a status of attendance. Both require
an effective evidence decision of `VERIFIED`. One of each per participation,
enforced by a one-to-one field. OD requires a reason; a rejection of either
requires a reason.

---

## Achievement

Created by Faculty (→ `DRAFT` → `PENDING_APPROVAL`) or by HOD/Admin (→
`APPROVED` immediately, since they already hold the approving authority and
routing their own record to their own queue would be an approval loop).

**Only `APPROVED` records are official.** Students never create achievements. A
verified participation does not become an achievement by itself — the record
exists only because someone deliberately created it. `achievement_date` must not
predate the event and must not be in the future. The link to participation is a
plain FK, because one event can legitimately yield more than one achievement.

---

## Notifications

In-app only, with **60-second polling** — no WebSockets.

- The recipient is always **derived from the business object**. There is no
  create endpoint, so no user can address a notification to anyone.
- A user reads **only their own** notifications, **including Admin**. There is no
  endpoint that returns another user's inbox.
- A unique dedupe key prevents duplicates.
- A notification failure is contained and **cannot roll back** the business
  transaction that triggered it — pinned by `test_transaction_safety.py`.
- `action_route` values are sanitized internal routes navigated through
  `Router.navigateByUrl`, which cannot leave the application.
- Exactly one polling timer exists no matter how many components mount it.

---

## Analytics

Ten scoped metric endpoints plus trend analysis, all drawing from
`apps/analytics/scope.py` — deliberately the **single place** where "what may
this user aggregate over" is decided.

- Scope is applied **before** aggregation, so out-of-scope rows never reach
  Python.
- A query parameter may **narrow** a scope and can never widen it; another
  student's id yields `404`, not their data.
- A rate with a **zero denominator is reported as `null`** with its counts, never
  as `0%`.
- A **college-wide event with no department** is handled explicitly and is not
  attributed to any department.
- Query counts are asserted by tests, so a reintroduced N+1 fails rather than
  being noticed in production.

---

## Reporting

12 report types × 3 formats (CSV, XLSX, PDF), from a **closed registry**. Report
type and format never come from user input used to build a path, a module name
or a filename; reports are rendered in memory and streamed, so nothing is
written to disk and there is nothing to traverse.

Every export is scoped to the caller whatever they request, carries
`Cache-Control: no-store` and a sanitized attachment filename, and writes a
`REPORT_GENERATED` audit entry. An empty report renders correctly with headers
and no rows.

---

## AI/ML

Four analytical components, **decision support only**. No AI function writes to
the database; no business service imports `apps.ai` (a structural assertion, so
an AI failure has no transaction to roll back); every entry point is wrapped in
a failure boundary that turns any exception into a controlled
`available: false`.

| Model | Output | What it is **not** |
|-------|--------|-------------------|
| KNN recommendation (`knn-similarity-v1`) | Similarity in (0, 1] over open events, with reasons | Not a probability. With no history, a documented deterministic cold-start ranking, labelled as such |
| Isolation Forest (`isolation-forest-v1`) | `LOW`/`MEDIUM`/`HIGH` risk signal with population thresholds | **Not proof of fraud**, not a probability, never grounds for rejection |
| K-Means engagement (`kmeans-engagement-v1`) | `LOW`/`MODERATE`/`HIGH` label, ordered by a documented formula, never by cluster id | Not an academic judgment, not a ranking |
| Statistical trends | Period-over-period change, direction, moving average | Plain arithmetic, not a model |

Anomaly features declare their **temporal status**, and no OUTCOME feature (the
decision on the record itself) is ever an input. Models are fitted on request —
always current, which is why they carry their own throttle scope.

There is **no ground-truth validation dataset**, so no accuracy, precision or
recall is claimed. There is **no face recognition and no image analysis** — the
models never see an image.

Detail: [`architecture/ai-architecture.md`](architecture/ai-architecture.md).

---

## Testing

68 backend test files; 50 frontend spec files. Backend tests run against the
**real Neon PostgreSQL database**, never SQLite, because constraints,
transaction semantics and type behaviour are part of what is being tested.
Authorization tests obtain a genuine JWT and make real HTTP requests — a test
that called a service directly would prove the service works, not that the
endpoint is protected.

Eleven cross-app security suites cover the role matrix, the IDOR matrix,
authentication, mass assignment, file-upload security, input hardening, security
configuration, secret hygiene across the whole repository, transaction safety,
timestamp boundaries and the full lifecycle.

Strategy: [`testing/testing-strategy.md`](testing/testing-strategy.md).
Security detail: [`testing/security-testing.md`](testing/security-testing.md).
Measured results: [`testing/test-results.md`](testing/test-results.md).

---

## Deployment

nginx → Gunicorn → Django, with NeonDB as a managed database. One service unit,
one nginx site, one static directory, one private media directory. No Docker, no
Kubernetes, no broker — none of them is needed, and none was added.

Configuration lives in [`../deploy/`](../deploy/): `gunicorn.conf.py`,
`nginx.conf.sample`, `ssepams.service`.

Guide: [`deployment/deployment-guide.md`](deployment/deployment-guide.md).
Checklist: [`deployment/production-checklist.md`](deployment/production-checklist.md).
Troubleshooting: [`deployment/troubleshooting.md`](deployment/troubleshooting.md).

**HTTPS is mandatory, not advisory** — live capture cannot function without it.

**Two things must be backed up, not one:** the Neon database *and*
`backend/media/`. Evidence images are files on disk, not database rows.

---

## Known Limitations

Stated plainly. Several are deliberate scope decisions rather than gaps.

### Verification is assisted, not tamper-proof

- The **device capture timestamp is client-supplied**. It is bounded against
  implausible future values, but a modified client could report a different
  time. There is no cryptographic capture attestation.
- **GPS coordinates are client-reported** and can be spoofed by a modified
  browser. This is exactly why venue distance warns rather than blocks, and why
  a human verifies the evidence. The system's claim is that a capture is *harder
  to fake and easier to review*, not that it is unforgeable.
- The **IndexedDB offline queue is not encrypted**. On a shared or compromised
  device a queued image and its coordinates could be read before upload.

### Architectural

- **Evidence storage is the local filesystem.** Private and authorization-gated,
  but single-host: a second application server would not see the first one's
  files. The storage abstraction exists so a private object store can replace it
  in one module; that work is not done.
- **Notifications poll every 60 seconds.** Up to a minute of latency.
- **Analytics are live application queries**, not a warehouse. Fine at this
  scale; a much larger dataset would want pre-aggregation.
- **AI models are fitted on request.** Always current; the most expensive reads
  in the system, hence their own throttle scope.
- **JWTs are stored in `localStorage`** — a documented trade-off with stated
  mitigations, not an oversight. See
  [`api/authentication.md`](api/authentication.md#client-side-token-storage--a-stated-trade-off).
- **The backend test suite is slow** (roughly one and three-quarter hours)
  because it runs against a remote database, and it is exposed to Neon's pooler
  behaviour. See the test results for how transient failures are classified.

### Deliberately not built

- **`Registration` has no `CONFIRMED` state.** The business rules never asked for
  one, and adding it would imply a confirmation step nobody performs.
- **There is no `CertificateArtifact` model.** Certificates remain separate and
  optional; this phase does not implement one. The natural future shape is
  `Evidence 1 → 0..1 CertificateArtifact` reusing the existing private storage —
  a design note, not existing code.
- **No browser end-to-end test suite** in this repository.
- **No AI accuracy metrics**, because there is no ground truth to measure
  against.
- **No independent penetration test.** The security suites cover the flaw classes
  the team identified; they are not an outside assessment.
- **No dependency CVE scanning in CI.** `npm audit --omit=dev` and `pip check`
  are run manually.
- **No face recognition. No QR-code attendance.** Neither is a gap; both were
  excluded by design.

---

## Future Enhancements

Possibilities, not commitments.

1. **Private object storage** (S3/GCS/Azure Blob) behind the existing
   abstraction — removes the single-host constraint. The replacement must keep
   three properties: no public ACL, no presigned URL handed to clients,
   retrieval only through the authenticated endpoint.
2. **`HttpOnly` refresh cookie + in-memory access token**, replacing
   `localStorage`.
3. **WebSocket or server-sent-event notifications**, replacing polling.
4. **A Playwright end-to-end suite** covering the camera and GPS workflow against
   real browser permission prompts.
5. **Client-side encryption of the offline capture queue.**
6. **Certificate artefacts**, as sketched above.
7. **Scheduled dependency CVE scanning in CI.**
8. **Pre-aggregated analytics** if the dataset outgrows live queries.
9. **Parallelised or sharded test runs** to cut the backend suite's wall-clock
   time.

---

## Final Verification Status

Measured on 2026-09-17, against the production-shaped configuration and the real
Neon database. Full detail, including the exact commands and how the run was
sequenced, is in [`testing/test-results.md`](testing/test-results.md).

| Check | Result |
|-------|--------|
| Backend test suite (`pytest -q --create-db`) | **782 passed, 0 failed** in 1:18:59 |
| Frontend test suite (Chrome Headless) | **317 of 317 SUCCESS** |
| TypeScript (`tsc --noEmit`) | Clean |
| Angular production build | Clean, **0 warnings**, 549.67 kB initial |
| `manage.py check` | No issues |
| `manage.py check --deploy` (`DEBUG=False`) | **No issues (0 silenced)** |
| `makemigrations --check --dry-run` | No changes detected |
| `migrate --plan` | No planned operations |
| `spectacular --fail-on-warn` | Clean, **100 operations** |
| `flake8` | **0 findings** |
| `pip check` | No broken requirements |
| `npm audit --omit=dev` | **0 vulnerabilities** |
| `collectstatic` | 163 copied, 469 post-processed |
| Production-mode server smoke (`curl`, `DEBUG=False`) | All checks passed |
| Real API end-to-end (`tests/e2e/api_lifecycle_smoke.py`) | **94 checks, 0 failed** |
| Live Admin user management against the real dev database | **49 checks, 0 failed**; `siteadmin`, `hodmca`, MCA and ARY01 unchanged |
| Repository secret scan | No secrets; only `user:password@ep-xxxx` placeholders |
| Browser E2E | **Not executed** — see below |

**No failure required classification.** The backend suite was clean on its
first complete run; there were no transient Neon connection drops to
distinguish from regressions.

### Browser E2E

> Browser E2E could not be executed because the environment does not provide the
> required browser tooling. No Chrome instance was connected to the browser
> automation extension.

The 301 frontend specs do execute in a real Chrome Headless engine, covering the
component, service, guard and interceptor code with the browser APIs mocked at
the boundary. That is not the same as driving the deployed interface through
real camera and geolocation permission prompts, and no claim is made that it is.

### The final audit pass

A later pass, triggered by a defect found in real-world manual testing, added
**Admin user management** (six Admin-only endpoints and the `/admin/users` page)
and fixed four further defects the audit turned up: two dashboard cards that sent
an Admin to a page contradicting the Registration ≠ Participation ≠ Attendance
distinction, a `page_size` query parameter that was silently ignored (so every
department and college dropdown truncated at 20), and two dropdowns that never
requested the full set. Detail: `../backend/README.md` → "Admin user management
and final audit pass", and `../PROJECT_HANDOFF.md` §14.

### Defects found and fixed in Phase 10

Nine, listed with their consequences in
[`../backend/README.md`](../backend/README.md#defects-found-and-fixed-in-this-phase).
The two that would have mattered most in production:

1. **`SECRET_KEY` silently fell back to a development value** under
   `DEBUG=False`, making every issued token forgeable by anyone who had read the
   repository. It is now a startup failure.
2. **There was no production static-file handling at all.** With `DEBUG=False`
   Django serves no static files, so the Django admin and the Swagger UI would
   have been broken on any real deployment.

A third was found late, while auditing the documentation against the code:
**private evidence images were streamed with no cache directive**, so a
browser could retain a student's participation photograph in its disk cache —
readable on a shared machine after logout. The report-download path had set
`no-store` since Phase 7; the image path had not.

### Readiness for demonstration and submission

The repository builds, starts, migrates, passes its full regression, passes the
Django deployment checks under a production configuration, and carries complete
architecture, API, database, testing, deployment and user documentation. Its
limitations are stated above rather than left to be discovered.
