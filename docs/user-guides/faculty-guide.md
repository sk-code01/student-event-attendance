# Faculty Guide

## Your role

You are the person who decides whether a student's participation evidence is
genuine. Everything downstream — attendance, on-duty leave, achievements —
depends on that judgment.

**What you can do**

- Review and verify participation evidence
- Reject evidence, or ask for a resubmission
- Request attendance on a student's behalf
- Request on-duty leave on a student's behalf
- Create achievement records
- View analytics and export reports for your scope

**What you deliberately cannot do**

- **Approve attendance or OD.** You request; the HOD approves. The separation is
  intentional: the person who verifies the evidence is not the person who grants
  the consequence.
- **Approve achievements.** You create; the HOD approves.
- **Manage events.** Event creation, publishing and cancellation belong to the
  HOD and Admin.
- **See outside your authorized scope.** Records outside it simply do not appear.

---

## Getting an account

Self-register with the role **Faculty** and your department. Your department's
HOD (or an Admin) approves the request; you can log in once they have.

---

## Reviewing evidence

### The queue

**Verification** lists the evidence awaiting a decision in your scope, with the
student, the event, when it was submitted, and any flags the system has raised.

Work oldest-first unless something is flagged. A student cannot have attendance,
OD or an achievement recorded until you have decided.

### What you are looking at

Open a record and you see:

| | |
|---|---|
| **The captures** | The primary photo plus any additional ones the student took |
| **Capture time** | The device's own timestamp — when the photo was taken |
| **Received time** | When the server received it. These differ for an offline capture that synced later, which is normal |
| **Location** | Latitude, longitude and the GPS accuracy the device reported |
| **Distance from venue** | Present when the event has coordinates |
| **Venue warning** | Raised when the capture is further from the venue than expected |
| **Version history** | Every earlier submission for this participation, and every decision on it |

The system has already refused anything captured on the wrong date, with no GPS,
or with accuracy worse than the configured threshold. What reaches you passed
those checks; your job is the judgment those checks cannot make.

### Deciding

Ask yourself: **does this photo show this student at this event?**

Look for the student *and* the surroundings — the venue, a banner, a stage, other
people. A close-up of a face against a blank wall passes every automated check
and still proves nothing.

| Decision | When | Requirement |
|----------|------|-------------|
| **Verify** | The evidence supports the claim | A reason is recorded |
| **Reject** | It does not, and a better photo cannot fix it | **Reason mandatory** |
| **Request resubmission** | It is inconclusive but the student can do better | **Reason mandatory** |

**Write the reason for the student, not for the file.** "Rejected" tells them
nothing. "The photo shows only your face; please recapture with the venue
banner visible behind you" tells them exactly what to do. Rejection and
resubmission reasons are shown to the student verbatim.

**Prefer resubmission over rejection** while the event is still running — the
student can capture again the same day. After the event date, they cannot, so a
rejection is final in practice. Bear that in mind.

### About the venue warning

A warning is **information, not a verdict**. Large campuses, changed rooms and
ordinary GPS drift all produce one. Weigh it with the photo. Do not reject on a
warning alone.

### About the AI risk signal

You may see a `LOW` / `MEDIUM` / `HIGH` risk signal on a record.

> This is a **statistical signal**, not a finding of fraud. It means the
> record's metadata is unusual compared with the rest of the population right
> now. It is not proof of anything, there is no ground truth behind it, and
> **it must never be the reason for a rejection.**

Use it to decide where to look first, and then decide from the evidence. Your
reason must always describe what you saw in the evidence.

### Versions and history

A resubmission creates a **new version**. Nothing is overwritten: earlier
captures, earlier decisions and their reasons all remain visible. Your decision
is appended to that trail with your name and the time.

If an HOD later overrides your decision, **your decision is not deleted**. Both
are visible, and the override is what counts downstream.

---

## Requesting attendance

Once evidence is verified, open the participation and choose **Request
attendance**. It goes to the HOD as `PENDING`; they approve or reject.

One attendance request per participation. Rejections come back with the HOD's
reason.

## Requesting on-duty leave

Same place, **Request OD** — and OD requires a **reason** describing why the
student should be excused (representing the department, an inter-college
competition, and so on). Write something the HOD can act on.

**Attendance and OD are independent.** Requesting one does not request the
other; approving one does not approve the other. Request whichever the situation
actually calls for, or both.

Both require a **verified** effective decision on the evidence. If an HOD
override changed the decision, the override is what governs.

---

## Creating achievements

For a student who won or placed at an event:

1. Open their verified participation.
2. Choose **Create achievement**.
3. Enter the title ("Inter-College Hackathon — First Place"), the type
   ("Competition", "Sports", "Cultural" — free text, kept consistent with the
   event categories) and the date.
4. Save as **draft**, then **submit for approval** when it is right.

The record is created as a **draft** you can still edit. Submitting sends it to
the HOD as `PENDING_APPROVAL`; only after their approval is it **official**.

The achievement date must not predate the event and must not be in the future.

**A verified participation does not become an achievement by itself.** Nothing
is automatic — the record exists only because you deliberately created it.

---

## Analytics and reports

**Analytics** covers your authorized scope: participation and verification
volumes, your pending queue, attendance and OD outcomes, achievements, and trends
over time.

A rate with no denominator is shown as "no data", never as `0%` — an empty
cohort has no meaningful rate.

**Reports** exports as **CSV**, **XLSX** or **PDF**:

| Report | Contents |
|--------|----------|
| Event | Per event, with registration and participation counts |
| Registration | Registrations and their status |
| Participation | Participations in scope |
| Verification | Submissions with the effective decision |
| Attendance/OD Summary | Per-event decision counts, side by side, never merged |
| Achievement | Achievements in scope |
| Student Participation / Achievement / Attendance / OD | Per-student detail |

Every export is limited to your scope, whatever you ask for, and every export is
recorded in the audit log.

---

## Notifications

The bell refreshes about once a minute. You are notified when a student submits
evidence in your scope, when an HOD acts on something you requested or created,
and when an HOD overrides one of your verification decisions.

You only see your own notifications.

---

## Good practice

- Review promptly — nothing downstream can happen until you decide.
- Write reasons the student can act on.
- Prefer resubmission while the event is still running.
- Treat the risk signal as a triage hint, never as grounds for rejection.
- Request attendance and OD separately and deliberately; do not request both by
  reflex.
- Create achievements only for real results, and only for verified
  participations.
