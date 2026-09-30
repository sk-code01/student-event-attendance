# Administrator Guide

## Your role

Admin is the only **system-wide** role. Everything an HOD can do in one
department, you can do anywhere, plus the things nobody else can: managing
departments and colleges, provisioning HODs, and reading the full audit trail.

That reach is why every Admin action is audited. Use the narrowest role that can
do the job — day-to-day approvals belong to the HOD who owns the department.

---

## Getting an Admin account

There is no self-registration for Admin. The first one is created on the server:

```bash
cd backend
./venv/bin/python manage.py createsuperuser
```

A Django superuser passes every role check. Afterwards, set that account's role
to `ADMIN` through the Django admin so its role claim matches its authority.

Keep the number of Admin accounts small, and keep their credentials in your
institution's password manager rather than in a file on the server.

---

## Departments and colleges

Both are reference data that everything else hangs off, and both are
Admin-managed.

**Departments** — name and code, both unique. Create them before provisioning
HODs or approving students, because every Student, Faculty and HOD belongs to
one.

**Colleges** — the conducting institution recorded on each event.

Neither can be deleted once it is referenced; deactivate instead. `is_active`
removes something from the choices offered for *new* records while leaving
existing records intact and readable. Deleting reference data that history
points at would break that history, which is why the database prevents it.

---

## Provisioning HODs

An HOD cannot depend on another HOD's approval, so there are two paths:

**Through the application** (normal):
the **Admin area** page (`/admin`) carries the Provision HOD form — username,
email, initial password, department. (Account *management* is the separate
Users page; provisioning creates the department's first HOD.)

**From the server** (bootstrap, before any Admin exists):

```bash
cd backend
./venv/bin/python manage.py provision_hod \
    --username hod_cse \
    --email hod.cse@example.edu \
    --password '<strong password>' \
    --department CSE
```

Both enforce the same rules: unique username and email, a password that passes
Django's validators, an existing department, and — **a department may have only
one active HOD**. To transfer the role, deactivate the outgoing HOD first.

Have the new HOD change their password at first login.

---

## User management

**Admin area → Users**, or the **Total Users** / **Active Users** cards on your
dashboard, which deep-link straight into it (the Active Users card arrives with
the active filter already applied).

The page shows every account in the system with counts across the top — total,
active, inactive, and a breakdown by role.

### Finding an account

Search by username, email, first or last name, and filter by role, department
or active status. All four work together, and all four are applied by the
server, so the page is as fast with four thousand accounts as with forty. The
filters live in the URL, so a filtered view can be bookmarked or pasted to
another administrator.

### What you can change

**Edit** lets you change email, first and last name, role and department.

Four rules are enforced by the server, not by the form, so they hold however the
request arrives:

- A **Student, Faculty or HOD must have a department.**
- **A department may have only one active HOD.** Promoting a second is refused
  with a message naming the account that already holds the post — deactivate or
  reassign that one first.
- **The system always keeps a usable Admin.** You cannot demote or deactivate
  the last active administrator.
- **You cannot deactivate your own account.**

Username cannot be changed here: other records refer to accounts by username in
the audit trail, and renaming would orphan that history. Django's `is_staff` and
`is_superuser` flags are also not editable through this page — those are
Django-level privileges that belong to `createsuperuser` and the Django admin.

### Activating and deactivating

**Deactivation is the off switch, never deletion.** A deactivated user cannot log
in, their existing access tokens stop working immediately, and their refresh
tokens are rejected — while every record they created stays intact and
attributable.

Use it for departed staff and graduated students. Do not delete users: the
database prevents it where history depends on them, and a deleted reviewer would
leave decisions unattributable.

### Resetting a password

**Reset password** opens a dialog for a new password and its confirmation. The
password is validated by Django's configured validators, hashed with
`set_password()`, and never displayed again — not on screen, not in the logs,
not in any API response.

Resetting also **signs out that account's existing sessions**: its outstanding
refresh tokens are revoked, so a reset genuinely takes the account back under
control rather than leaving an already-open session running. The page tells you
how many sessions were ended.

Hand the new password to the user through a channel you trust, and have them
change it at first login.

### Everything is audited

Every edit, activation, deactivation and password reset writes an audit entry
recording who did it, to which account, and which fields changed —
`ADMIN_USER_UPDATED`, `ADMIN_USER_ACTIVATED`, `ADMIN_USER_DEACTIVATED`,
`ADMIN_PASSWORD_RESET`. No password is ever written to that trail.

### The Django admin still exists

`/admin/` (Django's own admin) remains available for the things the application
deliberately does not expose: creating superusers, and low-level inspection.
Prefer the application's Users page for day-to-day work — it applies the business
rules above, and the Django admin does not.

Take care with role changes wherever you make them: making someone an HOD gives
them approval authority over a whole department, and changing a department moves
their entire scope.

---

## System-wide events

You can create events with **no department** — a college-wide event such as an
institution day. This is a supported case, not a gap:

- It is visible to every eligible student regardless of department.
- Analytics handles it explicitly rather than attributing it to an arbitrary
  department, so no department's figures are inflated by it.

Everything else about events — publishing, cancelling, the registration window,
the venue coordinates — works exactly as in the [HOD guide](hod-guide.md).

---

## Oversight

You can see every department's registrations, participations, evidence,
attendance, OD and achievements, and act anywhere.

**Prefer not to.** Approving a record in someone else's department bypasses the
person who owns that judgment. Reserve it for a genuine gap — an HOD on leave, a
department without one — and tell them afterwards.

One boundary you do **not** cross: **Admin does not see other users' personal
notifications.** `GET /api/v1/notifications/` returns only your own, for every
role including yours. There is no endpoint that returns someone else's inbox. If
you need to know what happened to a record, the audit log is the right
instrument.

---

## Audit log

`/api/v1/audit/`, or the Audit screen. Every entry records **actor, action,
description and timestamp**.

Recorded actions include authentication and account changes, registration
approvals and rejections, event lifecycle changes, evidence decisions and
overrides, attendance/OD/achievement decisions, and `REPORT_GENERATED` for every
report export.

The log is **append-only**. There is no API to write or edit an entry, and no
role — including yours — can alter it through the application.

Use it to answer "who did this, and when". Use it in particular to review your
own colleagues' Admin-level actions periodically; a reach this wide deserves a
second pair of eyes.

---

## Analytics and reports

System-wide versions of everything, plus:

- **Department Report** — per-department totals across the institution
- **System/Admin Report** — system-wide operational totals

Available as **CSV**, **XLSX** and **PDF**. Every export is audited.

When comparing departments, keep the denominators in view: a department with
five students and one participation is not outperforming one with five hundred
and eighty. A rate with a zero denominator is shown as "no data", never `0%`.

---

## System configuration

Configuration is environment-driven, in `backend/.env`, and is **not editable
from the application**. Changing any of it requires a restart.

| Variable | Effect |
|----------|--------|
| `APP_TIMEZONE` | The institution's calendar. Governs every "is today the event date" decision. |
| `MAX_GPS_ACCURACY_METERS` | The accuracy ceiling for a capture (default 50 m). **Raising this weakens every piece of evidence collected afterwards.** |
| `VENUE_WARNING_DISTANCE_METERS` | Distance past which a capture is flagged (default 200 m). Warning only — it never blocks. |
| `MAX_CAPTURE_FILE_SIZE` | Maximum capture image size (default 8 MB). If you raise it, raise nginx's `client_max_body_size` to match. |
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | Session lifetimes (30 minutes / 7 days). |
| `DJANGO_LOG_LEVEL` | Verbosity. |

Full reference: [`../../.env.example`](../../.env.example).

---

## Security monitoring

**Regularly**

- Review the audit log for unexpected Admin-level actions.
- Confirm the active Admin accounts are still the ones you expect.
- Confirm each department has exactly one active HOD.
- Check for accounts that should have been deactivated (departed staff,
  graduated students).

**Watch the logs for**

- Repeated failed logins against one account — the `auth` throttle limits this to
  10 attempts/minute, but a sustained pattern is worth knowing about.
- `429` bursts, which indicate either abuse or a misbehaving client.
- `django.security` warnings (suspicious operations, bad host headers).
- `django.request` errors, which are unhandled server-side exceptions.

**Never**

- Set `DJANGO_DEBUG=True` on a production host, even briefly. It exposes
  settings, stack traces and SQL to anyone who triggers an error, and it
  disables the HTTPS hardening.
- Run `manage.py seed_demo_data` against production. It refuses to run with
  `DEBUG=False` — do not work around that. Its accounts use a published password.
- Add a `/media/` location to the nginx configuration. That directory holds
  private evidence images, and serving it would expose every one of them.

**What is never logged**, at any level: passwords, JWTs, refresh tokens,
`Authorization` headers, the secret key, the database password.

---

## Routine operations

| Task | Command / place |
|------|-----------------|
| Service status | `systemctl status ssepams` |
| Live logs | `journalctl -u ssepams -f` |
| Health | `GET /api/v1/health/` |
| Readiness | `GET /api/v1/health/ready/` |
| Deployment check | `manage.py check --deploy` |
| Apply a release | [`../deployment/deployment-guide.md`](../deployment/deployment-guide.md#updating-a-running-deployment) |
| Something is broken | [`../deployment/troubleshooting.md`](../deployment/troubleshooting.md) |

**Two things to back up, not one.** The Neon database *and* `backend/media/`.
Evidence images are files on disk, not database rows — a database backup does not
contain them. Test a restore before you need one.
