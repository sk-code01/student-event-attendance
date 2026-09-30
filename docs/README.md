# Documentation Index

Documentation for the **Smart Student Event Participation and Attendance
Management System with AI-Based Analytics and Participation Verification**.

Everything here describes what the repository actually contains. Where a
capability is deliberately not built, it is listed as a known limitation
rather than described as if it existed.

## Where to start

| If you are a…              | Read first |
|----------------------------|------------|
| Developer joining the project | [`../README.md`](../README.md) → [`architecture/system-architecture.md`](architecture/system-architecture.md) |
| Evaluator / faculty guide  | [`FINAL_HANDOFF.md`](FINAL_HANDOFF.md) → [`testing/test-results.md`](testing/test-results.md) |
| System administrator       | [`deployment/deployment-guide.md`](deployment/deployment-guide.md) → [`deployment/production-checklist.md`](deployment/production-checklist.md) |
| API consumer               | [`api/api-overview.md`](api/api-overview.md) → [`api/endpoint-reference.md`](api/endpoint-reference.md) |
| Student / Faculty / HOD / Admin user | [`user-guides/`](user-guides/) |

## Contents

### Architecture
- [`architecture/system-architecture.md`](architecture/system-architecture.md) — the modular monolith, its layers, and why it is shaped this way.
- [`architecture/module-architecture.md`](architecture/module-architecture.md) — every Django app and Angular feature area, and what each owns.
- [`architecture/live-capture-architecture.md`](architecture/live-capture-architecture.md) — the browser camera + GPS participation workflow end to end.
- [`architecture/ai-architecture.md`](architecture/ai-architecture.md) — the four analytical models, their inputs, outputs, and limits.

### API
- [`api/api-overview.md`](api/api-overview.md) — conventions: versioning, pagination, filtering, errors, throttling.
- [`api/authentication.md`](api/authentication.md) — JWT issuance, refresh, rotation, logout, and the storage trade-off.
- [`api/endpoint-reference.md`](api/endpoint-reference.md) — every endpoint under `/api/v1/`, with roles and validation.

### Database
- [`database/database-architecture.md`](database/database-architecture.md) — PostgreSQL/Neon configuration, migrations, transactions, timezone handling.
- [`database/entity-relationship.md`](database/entity-relationship.md) — entities, relationships, cardinalities and constraints.

### Testing
- [`testing/testing-strategy.md`](testing/testing-strategy.md) — what is tested, at which level, and why.
- [`testing/test-results.md`](testing/test-results.md) — the actual final run, with counts and commands.
- [`testing/security-testing.md`](testing/security-testing.md) — the authorization, IDOR, upload and input-hardening suites.

### Deployment
- [`deployment/deployment-guide.md`](deployment/deployment-guide.md) — a reproducible production deployment sequence.
- [`deployment/production-checklist.md`](deployment/production-checklist.md) — the pre-go-live checklist.
- [`deployment/troubleshooting.md`](deployment/troubleshooting.md) — symptoms, causes and fixes.

### User guides
- [`user-guides/student-guide.md`](user-guides/student-guide.md)
- [`user-guides/faculty-guide.md`](user-guides/faculty-guide.md)
- [`user-guides/hod-guide.md`](user-guides/hod-guide.md)
- [`user-guides/admin-guide.md`](user-guides/admin-guide.md)

### Handoff
- [`FINAL_HANDOFF.md`](FINAL_HANDOFF.md) — the final project handoff document.

## Live API documentation

With the backend running, the OpenAPI schema and an interactive Swagger UI are
served from the application itself:

- Swagger UI — `http://localhost:8000/api/v1/docs/`
- OpenAPI schema (YAML) — `http://localhost:8000/api/v1/schema/`

The schema is generated from the code by drf-spectacular, so it cannot drift
from the implementation. Where this documentation and the schema disagree, the
schema is right.
