# HOD Guide

## Your role

You are the approving authority for your department. Everything you see and
everything you can act on is scoped to it — an Admin is the only system-wide
role.

**What you can do**

- Approve or reject student and faculty registration requests for your department
- Create, publish and cancel events
- Monitor registrations
- Review evidence, and **override** a Faculty verification decision
- **Approve or reject attendance**
- **Approve or reject on-duty requests**
- **Approve or reject achievements**
- View department analytics and export department reports

**Your scope**

Every list, every metric and every report is filtered to your department before
it reaches you. A record from another department returns "not found" — not
"forbidden" — so an identifier cannot be used to probe for its existence.

---

## Getting your account

An HOD is never self-registered. Either an Admin provisions you through the
application, or a system administrator runs
`manage.py provision_hod` on the server.

**A department has exactly one active HOD**, enforced by a database constraint.
To transfer the role, the outgoing HOD's account is deactivated first.

---

## Account management

**Registration requests** lists everyone who has self-registered for your
department and is waiting.

Check that the person is genuinely yours and that the role is right — Faculty
and Student are the only self-registerable roles — then:

- **Approve** — the account becomes active and they can log in immediately.
- **Reject** — **a reason is mandatory**, and the applicant sees it when they
  check their status. Write something specific: "not a student of this
  department", "duplicate account — use your existing one".

Approve promptly. Nobody can do anything until they can log in.

---

## Event management

### Creating an event

**Events → New**. You supply:

| Field | Note |
|-------|------|
| Title, description | |
| Event date | The **only** date on which participation can be captured |
| Venue | |
| **Venue coordinates** | Optional, but **supply them.** Without them the system cannot compute distance, and your Faculty lose the venue-warning signal entirely |
| Category | Free text, e.g. Technical, Cultural, Sports |
| Conducting college | |
| Registration window | Start and end date |

Events you create are scoped to your department.

### Publishing

A new event is a **draft** — invisible to students. Check every field, then
**Publish**: it becomes visible, registration opens according to the window, and
eligible students are notified.

**Get the date right before publishing.** The event date is the only day
participation evidence can be captured, and students plan around it.

### Cancelling

**Cancel** notifies everyone registered. Use it rather than deleting — the
record and its history remain.

### Monitoring registrations

Each event shows who has registered, who has cancelled, and how many have
submitted participation evidence. Use it before the event to gauge turnout and
after it to see who still has not submitted.

---

## Evidence review and override

You can review evidence in your department just as your Faculty can, and you can
decide on evidence they have not yet reached.

### Overriding a Faculty decision

When you disagree with a Faculty decision, use **Override**. Record the new
decision and **a mandatory reason**.

> **An override never deletes or edits the Faculty decision.** It is appended to
> the trail. Both decisions, both reviewers and both reasons remain permanently
> visible. Downstream workflows read the *effective* decision — your override
> when one exists, the Faculty decision otherwise.

Override where the evidence genuinely warrants it, and write a reason that
explains the disagreement. Your reason is a permanent record and your Faculty
can see it. Where the disagreement is about judgment rather than fact, a
conversation is usually a better instrument than an override.

Overriding a `VERIFIED` decision to `REJECTED` makes the participation ineligible
for attendance, OD and achievements. Overriding `REJECTED` to `VERIFIED` makes it
eligible.

---

## Attendance approval

**Attendance** lists what your Faculty have requested. Each shows the student,
the event, the requesting Faculty, and links to the underlying evidence.

Open the evidence before approving. You are approving the *consequence* of a
verification, and you should have seen what it was based on.

- **Approve** — recorded with your name and the time.
- **Reject** — **reason mandatory**, shown to the student and the Faculty.

Only participations whose effective evidence decision is `VERIFIED` can have
attendance requested at all.

## On-duty approval

**OD** works the same way, and the request carries the Faculty's reason for
seeking the excusal.

> **Attendance and OD are independent.** Approving attendance does not approve
> OD, and rejecting one does not reject the other. Decide each on its own merits
> — a student may deserve to be marked present without qualifying for on-duty
> leave.

---

## Achievement approval

**Achievements** lists what your Faculty have submitted for approval.

Check the title, type and date, and check that the underlying participation is
genuinely verified.

- **Approve** — the achievement becomes **official**. Only approved achievements
  count.
- **Reject** — **reason mandatory**.

An achievement you create yourself is approved immediately: you already hold the
approving authority, so routing your own record back to your own queue would be
an approval loop with no second reviewer.

---

## Analytics

Department analytics covers your department and nothing else:

- Events by status and category, with registration and participation volumes
- Participation and submission rates
- Verification outcomes and the current pending backlog
- Attendance and OD approval outcomes
- Achievements by status
- Trends: period-over-period change, direction, moving average

Two things worth knowing when you read the numbers:

- **A rate with a zero denominator is shown as "no data", never as `0%`.** An
  event nobody registered for has no participation rate, and reporting `0%`
  would be a false statement about engagement.
- **A college-wide event created by an Admin has no department.** It is not
  attributed to yours, so your departmental figures are not inflated by it.

An **engagement clustering** panel may label students low / moderate / high.
> These are descriptions of participation counts relative to other students right
> now — **not academic judgments, not rankings, and not grounds for any
> decision about a student.**

---

## Reports

Everything Faculty can export, plus the **Department Report** (your department's
totals). Available as **CSV**, **XLSX** and **PDF**.

Every export is scoped to your department whatever you request, and every export
is recorded in the audit log.

---

## Notifications

You are notified when someone self-registers for your department, when evidence
is submitted, when Faculty request attendance or OD, when Faculty submit an
achievement, and for the events you manage.

The bell refreshes about once a minute. You only see your own notifications.

---

## Good practice

- Review registration requests quickly — they block everything else.
- Always set venue coordinates; they are what give your Faculty the location signal.
- Publish only after the date is final.
- Open the evidence before approving attendance or OD.
- Decide attendance and OD separately.
- Override sparingly, and always with a reason that explains the disagreement.
- Approve achievements only when the participation is genuinely verified.
