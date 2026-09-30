# Frontend — SEAMS-AI

Angular 20 application (standalone components, no NgModules) for the student
event registration, participation, verification, attendance, OD,
achievement, notification, and analytics workflows described in the project
specification.

## Structure

```
src/app/
  core/        # singleton services, models, guards/interceptors (added as auth/authorization land)
  shared/      # reusable components, pipes, directives, validators (added as needed)
  features/    # route-level feature areas: auth, student, faculty, hod, admin,
               # events, participation, analytics, reports, ai (added per implementation phase)
```

Feature folders are created as each implementation phase introduces real
screens rather than pre-scaffolded as empty placeholders.

## Configuration

The API base URL is set per-environment in `src/environments/`:

- `environment.ts` — used by `ng serve` (defaults to `http://localhost:8000/api/v1`)
- `environment.prod.ts` — used by production builds (`/api/v1`, same-origin behind a reverse proxy)

## Development server

```bash
npm start
```

Open `http://localhost:4200/`. The root page performs a live connectivity
check against the Django backend's `/api/v1/health/` endpoint.

## Live participation capture (camera + GPS)

`features/participation/live-capture/` drives the student's "Mark
Participation" flow, backed by three `core/services/`:

- `camera.service.ts` — wraps the real `navigator.mediaDevices.getUserMedia()`
  and a `<canvas>` still-frame capture. No file picker / gallery upload is
  ever offered for participation photos — this is the only source of
  images, per the project's live-capture-only rule. Always call `.stop()`
  when leaving the capture page (component `ngOnDestroy`) to release the
  camera and its browser indicator.
- `geolocation.service.ts` — wraps the real `navigator.geolocation` API.
  Never fabricates coordinates and never falls back to IP-based
  geolocation; a denied/unavailable/timed-out location leaves submission
  blocked with no bypass.
- `offline-capture-queue.service.ts` — "capture now, upload later". Queued
  sessions (event id, captures' Blobs + their original device timestamp +
  GPS) are stored in **IndexedDB** (never `localStorage` — image Blobs
  don't belong there), keyed to the authenticated user's id so a different
  student logging into the same browser can never see or retry someone
  else's queued capture. No JWT/access token is ever stored in a queued
  record; sync requests go through the normal authenticated `HttpClient`
  (reusing the existing refresh-on-401 interceptor). Syncs automatically on
  the browser's `online` event and once eagerly at startup. A permanent
  (4xx) validation failure is marked `FAILED` and does not retry forever; a
  network/5xx failure stays `PENDING` for the next retry.
  **Known limitation**: IndexedDB here is not encrypted — a queued
  capture's image/coordinates could be read from browser storage before it
  uploads, on a shared/compromised device. Full client-side encryption is
  out of scope for this phase.

`Django never reads the device camera/GPS` — these two services are the
entire client-side data-collection surface; every field they produce
(coordinates, accuracy, timestamp, image) is re-validated server-side and
treated as untrusted evidence metadata, never as a trusted security value.

## Evidence versioning, Faculty verification, and HOD override (Phase 4)

`features/faculty/verification/` (queue + detail) and
`features/hod/verification/` (department queue + detail with override
controls) are backed by `core/services/evidence.service.ts`. Decision
actions (verify/reject/request-resubmission/override) live on
`EvidenceService` rather than a separate `VerificationService` — the
backend adapted the same consolidation onto `EvidenceViewSet` rather than
introducing a parallel `/verification/` resource, so a second frontend
service would only wrap the same endpoints with no distinct behavior.

- **Images are never a plain `<img src>` to a public URL.** Evidence
  capture images are served from an authenticated backend endpoint, so
  `shared/secure-image/secure-image.component.ts` fetches them via
  `HttpClient` (letting the existing auth interceptor attach the bearer
  token) as a `blob`, then renders a local `URL.createObjectURL()` — never
  a filesystem path or storage credential.
- **Faculty cannot see HOD override controls, and Students cannot see
  Faculty decision controls** — each role's component only renders the
  actions its own service/permissions actually allow; the backend remains
  the real enforcement point, per the project's standing "Angular guards
  are UX only" rule.
- **Student resubmission reuses `LiveCaptureComponent` verbatim** — no
  gallery upload, no manual coordinate/timestamp entry was introduced for
  Phase 4. `student/participation/:id/resubmit` routes into the same
  camera/GPS/review/submit state machine, parameterized by `route.data.mode
  === 'resubmit'`: it skips the normal Participation eligibility check
  (Participation is already `SUBMITTED`) and instead confirms the current
  `Evidence.status` is `RESUBMISSION_REQUIRED` before allowing capture, and
  submits directly against the existing participation id rather than
  opening a new one.
- **The offline capture queue extends to resubmissions.** A queued session
  now optionally carries `participationId` — set when queued from
  resubmission mode, so a delayed sync doesn't need to (and must not)
  re-open a fresh Participation for an event that's already been submitted
  once.

### Secure context requirement

`getUserMedia()` and `navigator.geolocation` both require a secure
context: HTTPS in production, or `http://localhost` for local development
(the one exception browsers make). There is no insecure-HTTP fallback —
if you deploy the Angular build anywhere other than localhost without
HTTPS, camera/GPS access will simply fail in the browser, by design.

## Testing

```bash
npm test -- --watch=false --browsers=ChromeHeadless
```

Requires Chrome/Chromium installed; set `CHROME_BIN` if it isn't auto-detected.
Camera/geolocation-dependent unit tests mock `navigator.mediaDevices` /
`navigator.geolocation` — mocking is confined to tests; the application
code always calls the real browser APIs.

## Build

```bash
npm run build
```

Output goes to `dist/frontend/`.

## Attendance, OD and achievements (Phase 5)

Three independent post-verification workflows, backed by three typed services
(`core/services/attendance.service.ts`, `od.service.ts`,
`achievement.service.ts`) that reuse the existing auth interceptor and role
guards - no authentication logic is duplicated, and no service exposes a way to
set a status directly.

- **Student** (`features/student/attendance`, `/od`, `/achievements`) - read-only
  views of their own records, showing status, who requested/reviewed, and the
  rejection reason where there is one. These templates render **no buttons at
  all**: a student never approves anything and never edits an official record.
  The achievements page separates official (APPROVED) records from
  pending/rejected ones so the two can never be confused.
- **Faculty** (`features/faculty/requests`, `features/faculty/achievements`) -
  lists verified participations and raises attendance/OD requests (OD requires a
  justification before the button enables), and records achievements that go to
  the HOD for approval. No approve/reject control is rendered anywhere in the
  Faculty area, not even for a record the same Faculty member created.
- **HOD** (`features/hod/attendance`, `/od`, `/achievements`) - the three
  approval queues, each splitting pending from decided. Rejection requires a
  reason before the confirm button enables, and decision buttons disable while a
  request is in flight so a double click cannot fire twice. The rows are
  replaced in place from the response rather than triggering a page reload, so a
  decided record stays visible with its new status and its history intact.
- **Admin** (`features/admin/oversight`) - read-only system-wide tables for all
  three, reached from the existing Admin shell. Nothing else in the Admin area
  was redesigned.

As everywhere else in this project, these role-scoped templates are UX only -
the backend's querysets and permission classes are the real boundary. The
Faculty pages filter to `status === 'VERIFIED'` purely to decide what to show;
the server independently re-resolves the effective verification decision from
the append-only decision history when a request is actually raised, and again
when it is decided.

## Notifications, dashboards and activity (Phase 6)

- **`core/services/notification.service.ts`** owns the unread count as a
  signal, so the bell in the app shell and the notifications page share one
  source of truth - marking something read updates the badge immediately with
  no second request and no stale count.
- **Polling lives in the service, not the component**, so there is exactly one
  timer no matter how many components are mounted; `startPolling()` is guarded
  against creating a duplicate interval. The app shell starts it on
  authentication and stops it on logout, which also zeroes the badge so the
  next user of the browser never inherits the previous user's count. The
  interval is 60s. **No WebSocket was introduced** - nothing in this phase
  needs sub-minute latency.
- **`shared/notification-bell/`** is one component reused by every role, added
  to the authenticated shell in `app.html`. It loads recent notifications only
  when opened, rather than on every page load.
- **`features/notifications/`** is the full backend-paginated list, with an
  unread filter and mark-read / mark-all-read. Notifications cannot be deleted:
  this phase preserves history and the API offers no destroy action.
- **`features/dashboard/`** is a single component for all four roles. It
  renders whatever cards the backend returns rather than switching on the role
  locally - the decision about what a role may see belongs to the server, and
  duplicating it here would create a second place to keep in step and a
  tempting place to "fix" a missing card by rendering data the backend did not
  intend to send.
- **`features/audit/`** is the audit trail view for HOD and Admin, with
  action / description / date filters. The route guard is UX only; the backend
  returns 403 to Student and Faculty regardless, and the component renders that
  as a clear message instead of an empty table.

`action_route` values come from the backend, which stores only single-slash
internal paths, so they are safe to hand to the router - there is no way for a
notification to carry an external redirect.

### Routes added

```
/dashboard        all authenticated roles
/notifications    all authenticated roles
/audit            HOD and Admin (guard is UX only; backend enforces)
```

## Analytics and reports (Phase 7)

- **`core/services/analytics.service.ts`** and **`report.service.ts`** are thin
  API clients. They contain **no arithmetic**: the backend decides what a role
  may see, how each value is computed and which filters are valid, so
  recomputing anything client-side would create a second, unauthoritative
  answer.
- **`features/analytics/`** is one page for every role. It renders whatever the
  backend returns rather than switching on the role to decide what to request -
  the server already scopes each response, and a per-role client implementation
  would duplicate the authorization rules. The single role-dependent call is the
  department comparison, which only HOD and Admin may make; for other roles it
  is not requested, and a 403 there is treated as "not available for you"
  rather than blanking the page.
- **`features/reports/`** lists only the report types the backend offered,
  previews the exact rows the export will contain, and downloads the file.
- **`shared/charts/`** holds `app-bar-chart` and `app-line-chart`, drawn as
  inline SVG. **No charting library was added** - `package.json` had none, and
  these views need comparative bars and a trend line rather than an interactive
  plotting toolkit. Inline SVG keeps the bundle unchanged and renders in the
  Karma DOM, so the tests assert on real output.

### Chart behaviour

Both charts handle the awkward shapes explicitly rather than assuming
well-formed data: empty data renders an empty-state message, a single point
renders a dot (a one-point polyline is invisible), an all-zero series renders a
flat baseline instead of dividing by zero, a blank category label renders as
`(none)`, and bar counts are capped. Bars are horizontal because the labels are
event titles and department names - long text that would be unreadable rotated
under a vertical axis.

### Downloads

Reports are fetched through `HttpClient` with `responseType: 'blob'` so the
existing auth interceptor attaches the bearer token - a plain anchor `href`
could not, and reports live behind an authenticated endpoint. The filename comes
from the server's `Content-Disposition`; only the final path segment is used, so
a malicious header cannot turn into a path. The object URL is revoked
immediately after the click.

### Rates

A rate of `null` means the denominator was zero and is rendered as an em dash,
never as `0%`.

### Routes added

```
/analytics    all authenticated roles (content scoped server-side)
/reports      all authenticated roles (types scoped server-side)
```

## AI decision support (Phase 8)

- **`core/services/ai.service.ts`** is three GETs (`/recommendations/`,
  `/anomalies/`, `/engagement/`) and nothing else. It has no method that names
  another student - the backend derives the subject from the authenticated
  user - and it never post-processes a score: the backend owns the model, the
  thresholds and the wording.
- **`shared/ai-disclaimer/`** renders the one sentence every AI view must
  carry. The text comes from the backend response when available, so the
  wording is defined in exactly one place, and falls back to the same sentence
  while loading or after a network error.
- **`features/ai/recommendations/`** (Student) renders the ranked list and the
  backend's reasons verbatim, shows the score as what the backend says it is
  (a similarity or a rank score, never a probability), and labels the
  cold-start case as a simple documented ranking rather than a model output.
  Its only action is a link to the ordinary event page - registering remains
  the student's own choice.
- **`features/ai/engagement/`** (every role) renders whichever keys the
  backend sent: a Student's own label and explanation, a Faculty
  distribution, HOD/Admin per-student rows. It does not switch on the role to
  decide what to show, so the authorization rule has exactly one home. The
  distribution is drawn in the backend's `label_order`, never by cluster id.
- **`features/ai/anomalies/`** (Faculty, HOD, Admin) lists risk signals with
  the specific features that crossed a threshold. **It has no approve, reject
  or dismiss control** - the only action is a link to the existing
  verification screen for the caller's role, and a test asserts that no button
  on the page carries such a label. The level filter is client-side display
  filtering of rows the backend already scoped; it never widens anything.
- **`features/ai/dashboard-panel/`** is the dashboard's insight strip. It is a
  separate child component with its own loading, unavailable and error state
  per card, so a model that cannot run never blanks the operational counts.
  Role is consulted only to avoid requesting endpoints the backend would
  refuse (recommendations are Student-only; risk signals are a staff view).

### States every AI view handles

loading / results / cold start (recommendations) / no actionable events /
`available: false` with `INSUFFICIENT_DATA` / `available: false` with
`MODEL_ERROR` / HTTP 403 ("not available for your role") / HTTP 404 ("not
within your scope") / network error. In every one of them the disclaimer stays
visible and nothing renders as `NaN`.

### Routes added

```
/recommendations   Student (backend answers 403 for staff regardless)
/engagement        all authenticated roles (content scoped server-side)
/anomalies         Faculty, HOD, Admin (guard is UX only; backend scopes rows)
```

## Hardening and quality assurance (Phase 9)

No feature changed. The frontend review confirmed: no `innerHTML`, no
`bypassSecurityTrust*`, no `eval`, no `console.log` in application code; the
only `href` assignment is the object-URL download; `returnUrl` and
`action_route` go through `Router.navigateByUrl`, which cannot leave the
application; tokens are the only `localStorage` entries (documented Phase 1
decision) and the offline capture queue uses IndexedDB; `environment.ts`
carries no secret; `npm audit --omit=dev` reports 0 vulnerabilities.

The one change is accessibility: every `<input>`, `<select>` and `<textarea>`
now has an accessible name — the event form's eight labels are paired with
their controls by `for`/`id`, the placeholder-only filters and rejection-reason
fields carry `aria-label`, and the two verification-decision textareas and the
override decision select are paired with their labels. A repository-wide check
finds no unlabelled control.

## Production build and deployment (Phase 10)

No component, service, route or style changed in this phase. The audit
confirmed the application was already production-ready, and this section
records what was verified and what a deployment has to do with the output.

### Verified

| Check | Result |
|-------|--------|
| `npx tsc -p tsconfig.app.json --noEmit` | Clean |
| `npm run build` (production configuration) | Clean, no warnings |
| Initial bundle | 549.53 kB raw / 112.14 kB transfer, inside the 600 kB warning budget |
| Lazy chunks | 54, one per lazily loaded route |
| `npm test -- --watch=false --browsers=ChromeHeadless` | 301 of 301 specs pass |
| `npm audit --omit=dev` | 0 vulnerabilities |
| `console.log` / `console.debug` in application code | None. The only console call is `main.ts`'s bootstrap `catch`, which is Angular's own scaffold |
| Hardcoded API URLs | None in the production build. `environment.prod.ts` uses the relative `/api/v1` |
| Credentials or secrets in source | None |

The one `localhost` string outside `environment.ts` is in
`camera.service.ts`, inside the message explaining that the camera needs a
secure connection — HTTPS *or* localhost. That is user-facing copy about a
browser rule, not a configuration value.

### Build output and where it goes

```bash
npm ci
npm run build          # production is the default configuration
```

Output: `dist/frontend/browser/`. That directory's **contents** (not the
directory itself) are what nginx serves from its document root.

The production configuration substitutes `environment.prod.ts`, which sets
`production: true` and `apiBaseUrl: '/api/v1'` — a *relative* base URL, which
assumes the reverse proxy serves the app and the API from **one origin**. That
is what `deploy/nginx.conf.sample` does, and it is why the browser makes no
cross-origin request in the standard deployment.

To serve the frontend from a different hostname than the API, change
`apiBaseUrl` in `environment.prod.ts` to the absolute API URL **before**
building, and add that frontend origin to the backend's `CORS_ALLOWED_ORIGINS`.

### What the deployment must get right

- **HTTPS is mandatory.** `getUserMedia` and `getCurrentPosition` are only
  available in a secure context. Over plain HTTP the live capture page reports
  `insecure-context` and the workflow cannot run at all. `localhost` is
  special-cased by browsers, which is why `ng serve` works without TLS.
- **`index.html` must be served with `Cache-Control: no-store`.** Build output
  is content-hashed (`outputHashing: "all"`), so the hashed assets can be
  cached for a year — but a cached `index.html` keeps pointing browsers at the
  previous deploy's script names.
- **Client-side routes need a fallback.** `try_files $uri $uri/ /index.html;`
  — without it, a reload on `/events/1` is a 404 from nginx.
- **Evidence images cannot be served as files.** The `secure-image` component
  fetches them through `HttpClient` so the auth interceptor can attach the
  bearer token, then renders an object URL and revokes it on destroy. There is
  no shareable URL for an evidence image, by design.

### Route guards are UX, not security

`auth.guard` and `role.guard` decide what to *render*. Every authorization
decision that matters is made by the API: DRF permission classes, role-scoped
querysets applied before aggregation, and object-level checks. A user who edits
their stored token's role claim changes what the navigation shows them and
nothing else — the backend reads the authoritative role from the database on
every request.
