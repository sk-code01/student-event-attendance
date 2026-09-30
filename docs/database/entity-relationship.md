# Entity Relationship

## The core chain

The whole system is one chain, and the cardinality at each link is the business
rule. Nothing in this chain is automatic — each arrow is a deliberate action by
an authorized person.

```
College ──1:N──► Event ◄──N:1── Department
                   │
                   │ 1:N
                   ▼
              Registration            "the student intends to attend"
                   │
                   │ 1 : 0..1         only if the student runs live capture
                   ▼
             Participation            "the student actually captured evidence"
                   │
                   │ 1 : 1
                   ▼
               Evidence               the versioned submission trail
                   │
     ┌─────────────┼──────────────────────────┐
     │ 1:N         │ 1:N                      │ 1:N (through versions)
     ▼             ▼                          ▼
EvidenceVersion  (history)          EvidenceVerification
     │                                  append-only decision trail
     │ 1:N
     ▼
EvidenceCapture   exactly one PRIMARY + N ADDITIONAL

           Participation
                 │
    ┌────────────┼─────────────┐
    │ 1:0..1     │ 1:0..1      │ 1:N
    ▼            ▼             ▼
Attendance   ODRequest     Achievement
```

> **The four concepts are distinct and never collapse into one another.**
> Registration ≠ Participation ≠ Attendance approval ≠ Achievement. A student
> who registers has not participated. A student who participated has not been
> marked present. A student marked present has no achievement. Each step
> requires its own authorized action, and the schema is built so that skipping
> one is impossible rather than merely discouraged.

## Entities

### Identity and organisation

**`College`** — `name` (unique), `code` (unique), `is_active`, `created_at`,
`updated_at`. The conducting institution for an event.

**`Department`** — `name` (unique), `code` (unique), `is_active`, `created_at`.
The department scope that HODs and Faculty are bound to.

> **A department does not belong to a college**, and a user therefore has no
> derivable college. `College` is attached to an **`Event`**
> (`Event.conducting_college`), which is where the business meaning lives: a
> college *conducts* an event. The Admin user-management table consequently
> shows department and not college — inventing a `Department → College` link, or
> a `User → College` field, purely to fill a UI column would add a relationship
> the business rules never asked for and a second place for department scope to
> disagree with itself. If an institution later genuinely needs college-scoped
> departments, that is a deliberate schema change with its own migration, not a
> convenience.

**`User`** (extends `AbstractUser`) — `username` (validated), `email` (unique),
`role` ∈ {`STUDENT`, `FACULTY`, `HOD`, `ADMIN`}, `department` (FK, nullable for
Admin), `is_active`.
*Constraint:* a department may have at most one **active** HOD.
*Note:* `is_active` is the deactivation switch — an inactive user cannot log in
and existing tokens stop working immediately.

**`RegistrationRequest`** — `user` (1:1), `role`, `department`, `status` ∈
{`PENDING`, `APPROVED`, `REJECTED`}, `requested_at`, `reviewed_by`,
`reviewed_at`, `rejection_reason`.
Created by self-registration; only `STUDENT` and `FACULTY` can be requested.
A rejection must carry a reason.

### Events and registration

**`Event`** — `title`, `description`, `event_date` (DateField), `venue`,
`category`, `conducting_college` (FK), `department` (FK, **nullable** — an
Admin-created college-wide event has none), `venue_latitude`,
`venue_longitude` (both optional), `created_by`, `status` ∈ {`DRAFT`,
`PUBLISHED`, `CANCELLED`}, `registration_start_date`, `registration_end_date`.

A null `department` is a real case, not a data problem: analytics handles it
explicitly rather than attributing the event to an arbitrary department.

**`Registration`** — `student` (FK), `event` (FK), `status` ∈ {`REGISTERED`,
`CANCELLED`}, `registered_at`, `cancelled_at`.
*Constraint:* unique per `(student, event)`.
*Note:* there is deliberately **no `CONFIRMED` state**. The business rules never
asked for one, and inventing it would imply a confirmation step that nobody
performs.

### Participation and evidence

**`Participation`** — `registration` (**1:1**), `student` and `event`
(denormalised for query performance and for the analytics joins), `status` ∈
{`DRAFT`, `SUBMITTED`, …}, `submitted_at`.
The one-to-one on `registration` is the database-level statement of
*"Registration 1 → 0..1 Participation"*.

**`Evidence`** — `participation` (**1:1**), `current_version` (FK, `SET_NULL`),
`status` ∈ {`SUBMITTED`, `UNDER_REVIEW`, `VERIFIED`, `REJECTED`,
`RESUBMISSION_REQUIRED`}.
`status` becomes meaningful only once the current version has actually been
submitted; the in-progress state is exposed as a computed serializer flag rather
than a sixth database enum value.

**`EvidenceVersion`** — `evidence` (FK), `version_number` (**server-controlled**,
unique per evidence), `submitted_by`, `submission_reason` (required on a
resubmission), `submitted_at`, `created_at`.
A resubmission creates a **new version**; it never edits the previous one. That
is what makes the history an audit trail rather than a current-state row.

**`EvidenceCapture`** — `evidence_version` (FK), `capture_role` ∈ {`PRIMARY`,
`ADDITIONAL`}, `object_reference` (private `FileField`), `mime_type`,
`file_size`, `sha256_hash`, `device_capture_timestamp`,
`server_received_timestamp` (`auto_now_add`), `latitude`, `longitude`,
`gps_accuracy`, `venue_distance`, `location_warning`, `validation_status`.
*Constraint:* exactly one `PRIMARY` per version.
*Note:* both timestamps are kept. The device timestamp establishes *when the
photo was taken* (and drives the event-date rule); the server timestamp
establishes *when we received it*, and is the only one the server vouches for.

**`EvidenceVerification`** — `evidence_version` (FK), `reviewer`, `decision` ∈
{`VERIFIED`, `REJECTED`, `RESUBMISSION_REQUIRED`}, `reason`,
`is_hod_override`, `created_at`.
**Append-only.** An HOD override is an additional row with
`is_hod_override = True`; the Faculty decision it supersedes is never
overwritten or deleted. The *effective* decision is derived — the override if
one exists, otherwise the Faculty decision — and every downstream workflow reads
the effective decision.

### Post-verification workflows

**`Attendance`** — `participation` (**1:1**), `status` ∈ {`PENDING`,
`APPROVED`, `REJECTED`}, `requested_by` (Faculty), `requested_at`,
`reviewed_by` (HOD/Admin), `reviewed_at`, `rejection_reason`.

**`ODRequest`** — `participation` (**1:1**), `reason` (**mandatory**), same
status and review fields.

Attendance and OD are **independent**. Approving one says nothing about the
other, and neither is derived from the other.

**`Achievement`** — `participation` (**FK, not 1:1**), `title`, `description`,
`achievement_type` (free text, matching the free-text `Event.category`
convention), `achievement_date`, `status` ∈ {`DRAFT`, `PENDING_APPROVAL`,
`APPROVED`, `REJECTED`}, `created_by`, `reviewed_by`, `reviewed_at`,
`rejection_reason`.

A plain FK because one event can legitimately yield more than one achievement
for the same student — a placing *and* a special award. No
`unique(student, type)` constraint is imposed: the rules do not ask for one and
it would reject legitimate records. Only `APPROVED` rows are official.

### Cross-cutting

**`Notification`** — `recipient` (FK), `notification_type` (20 values),
`title`, `message`, `related_entity_type`, `related_entity_id`, `action_route`
(sanitized internal route), `priority` ∈ {`NORMAL`, `HIGH`}, `dedupe_key`
(unique), `is_read`, `read_at`, `created_at`.
The recipient is always derived from a business object. There is no API to
create one, so no user can address a notification to anyone.

**`AuditLog`** — `actor` (FK, nullable so a deleted actor does not take the
record with it), `action`, `description`, `created_at`. Append-only; there is no
write endpoint.

## Derived relationships

These are computed, not stored. Storing them would create a second source of
truth that could disagree with the first.

| Derived value | Derived from |
|---------------|--------------|
| Effective evidence decision | Latest `EvidenceVerification` with `is_hod_override=True`, else the Faculty row |
| Event completion | `event_date < today` in `APP_TIMEZONE`, on a `PUBLISHED` event |
| Participation eligibility | Registration exists + event is published + `event_date == today` + no submitted evidence yet |
| Attendance/OD eligibility | Effective evidence decision is `VERIFIED` |
| Student → achievements | `Achievement → Participation → Event → Student` — no denormalised copy of student/event on `Achievement` |
| Unread notification count | `COUNT` over the recipient's unread rows |

## Certificate artefact — deferred, not implemented

There is **no `CertificateArtifact` model in this system.** The specification
treats a participation certificate as separate from and optional to evidence,
and this phase does not implement one. If it is added later, the natural shape
is `Evidence 1 → 0..1 CertificateArtifact` reusing
`apps/participation/storage.py` so a certificate inherits the same private
storage and the same authenticated retrieval path as a capture. That is a
design note, not a description of existing code.

## Cardinality summary

| Relationship | Cardinality | Enforced by |
|--------------|-------------|-------------|
| College → Event | 1 : N | FK |
| Department → Event | 1 : N (nullable) | FK |
| Department → User | 1 : N (nullable for Admin) | FK |
| User → RegistrationRequest | 1 : 1 | `OneToOneField` |
| Event → Registration | 1 : N | FK + unique(student, event) |
| **Registration → Participation** | **1 : 0..1** | `OneToOneField` |
| **Participation → Evidence** | **1 : 1** | `OneToOneField` |
| **Evidence → EvidenceVersion** | **1 : N** | FK + unique(evidence, version_number) |
| **EvidenceVersion → EvidenceCapture** | **1 : N** | FK + unique PRIMARY per version |
| **Evidence → EvidenceVerification** | **1 : N** (via versions) | FK, append-only |
| Participation → Attendance | 1 : 0..1 | `OneToOneField` |
| Participation → ODRequest | 1 : 0..1 | `OneToOneField` |
| Participation → Achievement | 1 : N | FK |
| User → Notification | 1 : N | FK |
| User → AuditLog | 1 : N (nullable actor) | FK |
