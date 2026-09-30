# Authentication

JWT bearer tokens, issued by `djangorestframework-simplejwt`. There are no
session cookies on the API, and no other authentication scheme is supported.

## Token lifetimes

| Token | Lifetime | Setting |
|-------|----------|---------|
| Access | 30 minutes | `JWT_ACCESS_MINUTES` |
| Refresh | 7 days | `JWT_REFRESH_DAYS` |

Refresh tokens **rotate** (`ROTATE_REFRESH_TOKENS = True`): each refresh returns
a new refresh token and **blacklists the old one**
(`BLACKLIST_AFTER_ROTATION = True`). A stolen refresh token therefore becomes
useless the moment the legitimate client refreshes, and a replayed old token is
rejected.

## Obtaining tokens

```http
POST /api/v1/auth/token/
Content-Type: application/json

{ "username": "student1", "password": "…" }
```
```json
{ "access": "eyJ…", "refresh": "eyJ…" }
```

**Distinguished failure reasons.** A plain wrong password is a generic `401`.
An account that exists but cannot log in gets a specific, non-enumerating
reason, because "your password is wrong" would be actively misleading:

| Condition | Code | Message |
|-----------|------|---------|
| Registration awaiting HOD review | `account_pending` | *Your account is pending HOD approval.* |
| Registration rejected | `account_rejected` | *Your registration request was rejected.* |
| Account deactivated | `account_inactive` | *This account has been deactivated.* |
| Wrong credentials | — | SimpleJWT's generic `401` |

All four are `401`, so an attacker cannot distinguish "no such user" from "wrong
password" by status code.

Login is throttled at the `auth` scope — 10 requests/minute.

## Using the access token

```http
GET /api/v1/dashboard/
Authorization: Bearer <access token>
```

A missing, malformed, expired or blacklisted token is `401`. Nothing about
*why* is leaked beyond simplejwt's standard codes.

## Refresh

```http
POST /api/v1/auth/token/refresh/
{ "refresh": "eyJ…" }
```
```json
{ "access": "eyJ…", "refresh": "eyJ…" }
```

The Angular interceptor does this automatically on a `401`, then replays the
original request once. Concurrent 401s share a single in-flight refresh rather
than each triggering one; if the refresh itself fails, the session is cleared
and the user is sent to `/login`.

## Logout

```http
POST /api/v1/auth/logout/
Authorization: Bearer <access token>
{ "refresh": "eyJ…" }
```

Returns `205 Reset Content`. The refresh token is blacklisted server-side. The
**access token remains valid until it expires** — that is inherent to stateless
JWT and the reason the access lifetime is short. Clients must discard it
locally, which the Angular `AuthService.clearSession()` does.

## Token claims and the authorization boundary

The token carries `role` and `department_id` claims. They exist so the client
can render the right navigation immediately after login.

> **The claims are never the authorization decision.** Every request loads the
> `User` row and reads the authoritative role and department from the database.
> A token whose claims were edited grants nothing. `GET /api/v1/users/me/` is
> the authoritative identity endpoint for the client, and
> `backend/tests/test_authentication_security.py` pins this behaviour.

## Deactivated users

Setting `is_active = False` stops a user immediately:

- New logins are rejected with `account_inactive`.
- Existing access tokens stop working, because DRF's `JWTAuthentication` loads
  the user and rejects an inactive one.
- Refresh is rejected for the same reason.

There is no window in which a deactivated user keeps working access.

## Self-registration and approval

```
POST /api/v1/auth/register/     role ∈ {STUDENT, FACULTY}, department required
        │
        ▼  User created with is_active = False + a PENDING RegistrationRequest
   notification to the department's HOD
        │
   HOD/Admin reviews:  GET  /api/v1/users/registration-requests/
        ├── POST /api/v1/users/registration-requests/{id}/approve/  → is_active = True
        └── POST /api/v1/users/registration-requests/{id}/reject/   → reason required
        │
        ▼  the applicant can check their own status without an account:
   POST /api/v1/auth/registration-status/   { "username": …, "email": … }
```

`role` is a restricted choice field: **only `STUDENT` and `FACULTY` can be
self-registered.** An HOD or Admin can never be created through this endpoint,
no matter what is posted.

## Provisioning an HOD

An HOD cannot depend on another HOD's approval, so there are two bootstrap
paths, both restricted:

| Path | Who | When |
|------|-----|------|
| `POST /api/v1/users/provision-hod/` | Admin only (`IsAdminRole`) | Normal operation |
| `python manage.py provision_hod --username … --email … --password … --department <CODE>` | Anyone with server shell access | Before any Admin exists |

Both enforce the same rules: the username must be valid and free, the email
unique, the password must pass Django's validators, and **a department may have
only one active HOD**.

## Password change

```http
POST /api/v1/users/me/password/
{ "current_password": "…", "new_password": "…" }
```

The current password is required; the new one is run through Django's validator
chain.

## Client-side token storage — a stated trade-off

The Angular app stores the access and refresh tokens in `localStorage`.

**Why:** it survives a page reload, works across tabs, and needs no cookie/CSRF
machinery on a cross-origin API.

**The cost:** `localStorage` is readable by JavaScript, so a successful XSS on
the frontend could exfiltrate a token. An `HttpOnly` cookie would not be, but it
would bring CSRF exposure and cross-origin cookie handling in exchange.

**What mitigates it here:** Angular escapes interpolated content by default; no
`innerHTML` or `bypassSecurityTrust*` is used with user-supplied content; access
tokens live 30 minutes; refresh tokens rotate and blacklist on use; and logout
blacklists server-side.

This is documented rather than redesigned at this stage of the project. Moving
to `HttpOnly` refresh cookies with an in-memory access token is listed as a
future enhancement in [`../FINAL_HANDOFF.md`](../FINAL_HANDOFF.md).

## What is never logged

Passwords, access tokens, refresh tokens, the `Authorization` header, the
`SECRET_KEY` and the database password are never written to any log, at any
level. The `apps.security` logger records *who did what to which object* — ids,
usernames, roles and action names — and nothing else.
