# Security Testing

Eleven cross-app suites in `backend/tests/` plus per-app IDOR suites. Every one
drives the real HTTP API with a real JWT against a real PostgreSQL database — a
test that called a service function directly would prove the service works, not
that the endpoint is protected.

---

## The conventions being enforced

Two rules run through every suite:

1. **An object outside the caller's visible queryset returns `404`.** Not `403`.
   A `403` on a record you cannot see confirms it exists, which is an
   information leak in itself.
2. **A visible object with a forbidden action returns `403`.**

Two deliberate deviations exist (registration-request review by another
department's HOD, and the bare draft-event primary-key check on registration).
Both are **pinned as they are** in `test_idor_matrix.py`, so a future change to
either is a conscious decision rather than an accident.

---

## `test_authorization_matrix.py` — the role matrix

Every role × every protected action. Specifically:

| Attempt | Expected |
|---------|----------|
| Unauthenticated request to any protected endpoint | `401` |
| Student verifies evidence / approves anything / creates an achievement | `403` |
| Student manages events | `403` |
| **Faculty approves attendance or OD** | `403` — Faculty request, HOD approves |
| **Faculty approves an achievement** | `403` |
| Faculty manages events | `403` |
| HOD acts outside their department | `404` |
| Admin acts anywhere | allowed, and audited |

The Faculty rows are the ones that matter most: they pin the separation between
verifying evidence and granting its consequence.

## `test_idor_matrix.py` — insecure direct object references

Across **every** resource type — registration, participation, evidence, capture
image, attendance, OD, achievement, notification:

- Student A2 (same department) and Student B (other department) against Student
  A's records → `404` on every detail endpoint.
- The same two against every mutating action on Student A's records → never
  `200`.
- A student attempting any staff decision → refused.
- Faculty and HOD of department B against department A's records → `404`.
- Department B staff attempting decisions on department A records → refused.
- An HOD cannot reach another department **through filter parameters** — query
  parameters may narrow a scope, never widen it.
- Faculty cannot perform HOD decisions even within their own department.
- Non-existent ids are `404` even for Admin.
- Non-numeric ids never match a route and never produce a `500`.

## `apps/accounts/tests/test_admin_user_management.py`

The Admin user-management endpoints are the only place one account may change
another, so they are tested as a privilege boundary:

- Unauthenticated → `401`; Student, Faculty and HOD → `403` on **every** read
  and every write, including by guessing the path directly.
- `username`, `is_staff` and `is_superuser` are ignored when posted — the
  mass-assignment defence applies here too.
- `PUT` is refused (`405`); only `PATCH` is accepted.
- **The last active Admin cannot be demoted or deactivated**, and an Admin
  cannot deactivate their own account.
- A second active HOD for one department is refused with a `400` naming the
  incumbent, and a database-level collision (two concurrent promotions) is
  converted to a `400` whose message does not leak the index name.
- A Django superuser's role cannot be changed.
- The list response contains no `password`, hash, or token; the password-reset
  response contains no password material; the stored value is hashed; a weak
  password is refused by Django's validators; and the audit entry records the
  reset **without** the password.
- A reset **revokes the target's outstanding refresh tokens**, so a session
  opened before the reset cannot be replayed.

## `test_authentication_security.py`

- A tampered, malformed, expired or blacklisted token is rejected.
- **An edited `role` claim grants nothing** — the authoritative role is read from
  the database on every request.
- A deactivated user's existing access token stops working immediately.
- A rotated refresh token cannot be replayed.
- Logout blacklists the refresh token.
- Login does not reveal whether a username exists.

## `test_mass_assignment.py`

Every server-set field is read-only and is **silently ignored** when posted:
`created_by`, `requested_by`, `reviewed_by`, `status`, every `*_at` timestamp,
`version_number`, `sha256_hash`, `server_received_timestamp`.

A client cannot post `{"status": "APPROVED"}` into a create call and skip the
workflow, cannot set `created_by` to someone else, and cannot choose an evidence
version number.

## `test_file_upload_security.py`

The capture upload is the only place a user supplies bytes, and it is tested as
hostile input:

| Test | Asserts |
|------|---------|
| SVG containing a script | Rejected, whatever it claims to be |
| HTML, JavaScript and executable content | Rejected |
| A lying `Content-Type` header | **The bytes decide, not the header** |
| Unsupported real image formats (GIF, BMP, TIFF) | Rejected |
| Empty, truncated, and over-size-dimension files | Rejected |
| Over-byte-count file | Rejected cleanly with a `400`, not a crash |
| Hostile filenames (`../../etc/passwd`, NUL bytes, absolute paths) | **Never reach the storage path** — the key is server-generated |
| Polyglot JPEG with trailing script | Stored as an image only |
| `capture_role` | A closed choice; arbitrary values rejected |
| Stored files | Live only under the private storage root |

## `test_input_hardening.py`

| Test | Asserts |
|------|---------|
| SQL and script payloads in text filters | Treated as inert literals; the ORM parameterises |
| Non-numeric values in numeric filters | `400`, never `500` |
| Bad event ids on the eligibility endpoint | `400` |
| Pagination parameters | Hardened against negative, huge and non-numeric values |
| Unknown report type, and path traversal in the report path | `404` — the registry is a closed allowlist |
| Oversized and binary-junk request bodies | `400`, never `500` |

NUL bytes in a path or query string are answered `400` by
`RejectNullBytesMiddleware` before any view runs — PostgreSQL text columns
cannot store them, so without this they would surface as a `500`. That
middleware exists because this suite found the hole.

## `test_security_configuration.py`

Asserts the running configuration and the repository itself:

- Every response carries `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
  `Cross-Origin-Opener-Policy: same-origin`.
- Report downloads are `no-store` with a sanitized `Content-Disposition`
  filename matching `[A-Za-z0-9._-]+`.
- **`MEDIA_ROOT` is not served by any URL** — four different paths, including a
  traversal attempt through `/static/`, all return `404`.
- **An evidence image is never cacheable** — the streamed image carries
  `Cache-Control: no-store`, so a browser cannot leave a participation
  photograph in its disk cache on a shared machine.
- **No response exposes a storage path** — an evidence response contains the API
  path, never `participation_captures` or `MEDIA_ROOT`.
- Unhandled paths do not leak a debug page or a traceback.
- Settings come from the environment; the obsolete `SECURE_BROWSER_XSS_FILTER` is
  absent.
- CORS is an explicit allowlist with no wildcard, and
  `CORS_ALLOW_ALL_ORIGINS` is off.
- The production branch enables `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
  `CSRF_COOKIE_SECURE` and HSTS.
- JWT rotation and blacklisting are on, and the access lifetime is ≤ 1 hour.
- The default permission class is `IsAuthenticated` and throttling is active.

### Secret hygiene — the whole repository

`SecretHygieneTests` walks every `.py`, `.ts`, `.html`, `.json`, `.md`, `.yaml`,
`.txt`, `.cfg`, `.ini` and `.example` file in the repository (excluding
`node_modules`, `venv`, `dist`, `media`, `.git`) and fails on:

- a PostgreSQL connection string with embedded credentials,
- an AWS access key id,
- a PEM private key block,
- anything shaped like a JWT.

It also asserts that `.env` and `backend/.env` are gitignored, that
`.env.example` contains only placeholders with a **blank** `DATABASE_URL`, and —
via `git ls-files` — that `backend/.env` is **not tracked**.

When it fails it prints the file and line number only, **never the value**. A
test that echoed a leaked secret into CI output would leak it twice.

## `test_transaction_safety.py`

- A notification failure cannot roll back the business transaction that
  triggered it.
- A partially applied workflow transition is impossible.
- Concurrent approvals do not double-apply.

## `test_timestamp_boundaries.py`

The event-date rule at its edges: midnight in `APP_TIMEZONE`, clock skew beyond
the 5-minute future tolerance, a same-day capture synced the following day
(accepted), and a wrong-day capture uploaded promptly (rejected).

## `test_workflow_lifecycle.py`

The whole chain end to end with real tokens at every step, asserting both that
each authorized actor can proceed and that each unauthorized actor cannot.

## `apps/ai/tests/test_security_and_safety.py`

- No business service imports `apps.ai` — a structural assertion, so an AI
  failure can never roll back a workflow.
- Every AI failure is contained and returns a controlled payload.
- No AI endpoint widens the caller's scope.
- No identity leakage across scope boundaries in any AI response.

---

## What this does not cover

- **No independent penetration test.** These suites cover the classes of flaw
  the team identified. They are not an outside assessment.
- **No automated browser security testing** (CSP enforcement in a real browser,
  clickjacking in a real frame).
- **No dependency CVE scanning in CI.** `npm audit --omit=dev` and `pip check`
  are run manually; there is no scheduled scan.
- **No rate-limit or DoS testing** beyond the throttle configuration being
  asserted as present.
- The JWT-in-`localStorage` trade-off is documented, not eliminated. See
  [`../api/authentication.md`](../api/authentication.md#client-side-token-storage--a-stated-trade-off).
