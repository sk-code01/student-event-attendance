# Diagrams

This directory holds no image files. The project's structural and behavioural
diagrams are maintained as text inside the documents they belong to, so that
they are versioned, diffable, and cannot drift out of step with the prose around
them the way an exported image does.

| Diagram | Where |
|---------|-------|
| Deployment / system context | [`../architecture/system-architecture.md`](../architecture/system-architecture.md) |
| Module dependency graph | [`../architecture/module-architecture.md`](../architecture/module-architecture.md) |
| Live-capture state machine and offline-queue flow | [`../architecture/live-capture-architecture.md`](../architecture/live-capture-architecture.md) |
| Entity relationships and cardinalities | [`../database/entity-relationship.md`](../database/entity-relationship.md) |
| End-to-end workflow / activity flow | [`../../README.md`](../../README.md#complete-workflow) |
| Registration-approval and authentication flow | [`../api/authentication.md`](../api/authentication.md#self-registration-and-approval) |

The one machine-generated artefact is the **OpenAPI schema**, produced from the
code rather than drawn by hand:

```bash
cd backend
python manage.py spectacular --file schema.yaml
```

It is also served live at `/api/v1/schema/`, with a browsable Swagger UI at
`/api/v1/docs/`. Because it is generated, it cannot disagree with the
implementation — and it is the right input to any diagramming tool that wants to
render the API.

If exported diagrams are needed for a report or a presentation, this directory
is the place for them; keep the text version above as the source of truth and
regenerate the images from it rather than editing them independently.
