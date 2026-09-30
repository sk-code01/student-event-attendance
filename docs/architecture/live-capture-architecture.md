# Live Participation Capture Architecture

The live capture workflow is the part of this system that makes participation
*verifiable* rather than merely *claimed*. It replaces "upload a photo you have
lying around" with "take a photo, right now, at this event, with a GPS fix".

There is **no QR-code attendance** and **no face recognition** anywhere in this
system. Verification is a human judgment made by Faculty, supported by the
metadata described below.

## The twenty finalized rules

| # | Rule | Where it is enforced |
|---|------|----------------------|
| 1 | A capture is valid only on the event's exact date | `validate_device_timestamp_for_event` (backend) |
| 2 | One primary live capture is mandatory | DB `UniqueConstraint` on `(evidence_version, capture_role=PRIMARY)` + submit-time check |
| 3 | Additional live captures are optional | `EvidenceCapture.Role.ADDITIONAL`, unbounded |
| 4 | Gallery upload is not allowed | No file input in the UI; frames come only from `canvas.toBlob()` on the live `<video>` |
| 5 | The camera must be the browser's live camera | `navigator.mediaDevices.getUserMedia`, no fallback path |
| 6 | GPS is mandatory | `validate_gps` rejects a missing latitude/longitude |
| 7 | Permission denial blocks submission | Typed `CameraError` / `GeoError`; the UI has no bypass |
| 8 | GPS accuracy worse than the threshold blocks submission | `validate_gps` against `MAX_GPS_ACCURACY_METERS` (default 50 m) |
| 9 | Venue distance is a warning only | `compute_venue_distance` sets `location_warning`; it never raises |
| 10 | Student and surroundings should be visible for review | Rear camera (`facingMode: 'environment'`), minimum 100×100 px, image shown full-size to the reviewer |
| 11 | Retakes before submission are unlimited | Frames are held in component state until submit |
| 12 | Offline capture queues locally | IndexedDB store `ssepams-offline-captures` |
| 13 | The queue retries when connectivity returns | `window.addEventListener('online', …)` + a sync on construction |
| 14 | Backend acknowledgement determines success | The queued record is deleted only after the submit call resolves |
| 15 | The device capture timestamp is preserved | `EvidenceCapture.device_capture_timestamp` |
| 16 | The server receipt timestamp is authoritative for *receipt* | `EvidenceCapture.server_received_timestamp` (`auto_now_add`) |
| 17 | A late upload cannot make an invalid capture valid | Rule 1 compares the *device* timestamp's local date to the event date, not "today" |
| 18 | Certificates remain separate and optional | Not part of evidence; see Known limitations |
| 19 | No QR attendance | Not implemented anywhere |
| 20 | No face recognition | Not implemented anywhere |

## Client-side flow

`frontend/src/app/features/participation/live-capture/` is a small state
machine. Each state corresponds to exactly one thing the student can see or do:

```
CHECKING_ELIGIBILITY
   │  GET /api/v1/participations/eligibility/?event=<id>
   ├─► NOT_ELIGIBLE                (not registered / not the event date / already submitted)
   ▼
CAMERA_PERMISSION_REQUIRED ──► LOCATION_PERMISSION_REQUIRED ──► LOCATION_ACQUIRING
   │                                                                 │
   │  any permission denied ─────────────────────────► ERROR (no bypass)
   ▼                                                                 ▼
READY_TO_CAPTURE ──shutter──► CAPTURE_PREVIEW ──keep──► REVIEW ──submit──► SUBMITTING
       ▲                            │                     │                   │
       └────────── retake ──────────┘                     │            online │ offline
                                       add another capture┘                   ▼
                                                              SUBMITTED   OFFLINE_QUEUED
```

**Eligibility is checked first**, so a student who cannot capture is told why
before the browser ever asks for camera or location permission.

**Permissions are requested in order** — camera, then location — and each has
its own message when denied, because "we can't see your camera" and "we can't
see where you are" need different remedies from the user.

**Secure context is required.** `getUserMedia` and `getCurrentPosition` are
only available on HTTPS or `localhost`. `CameraService.start()` checks
`window.isSecureContext` first and raises `insecure-context` with a message
saying so, rather than letting the browser fail opaquely. This is why the
production deployment guide treats HTTPS as mandatory, not advisory.

**Unsupported browsers degrade explicitly.** A missing
`navigator.mediaDevices.getUserMedia` or `navigator.geolocation` produces
`unsupported` — a clear message, not a silent dead end.

**Camera release.** `CameraService.stop()` stops every track on retake, on
submit and on navigation away. Leaving a `MediaStream` open keeps the browser's
camera indicator lit and is a privacy problem in its own right.

## The offline queue

```
capture (offline)  ─►  IndexedDB: { id, userId, eventId, participationId?, captures[], status, lastError }
                              │
   'online' event  ──────────►│  syncAll()
                              ▼
                       POST participation (if needed) → POST captures → POST submit
                              │
                    success ──┴──► delete record      failure ──► status: FAILED, lastError recorded
```

Four properties matter here:

- **No token is ever stored.** A queued record holds image blobs and capture
  metadata only. Sync goes through the normal `HttpClient`, so the auth
  interceptor attaches whatever session is valid *at sync time* — an expired
  token is refreshed, and a logged-out user simply does not sync.
- **The queue is scoped to the authenticated user.** Each record carries the
  `userId` it was created under, and sync only processes records belonging to
  the currently authenticated user. A different student logging into the same
  browser cannot see or trigger another student's queued capture.
- **A stale queued capture cannot bypass the date rule.** The device capture
  timestamp is stored with the record and sent at sync time; the backend
  compares *that* timestamp's local date to the event date. A capture taken on
  the wrong day is rejected no matter how long it sat in the queue, and a
  capture taken on the right day is still accepted if it syncs the next morning.
- **IndexedDB is not encrypted.** This is a stated limitation: on a shared or
  compromised device, a queued image and its coordinates could be read from
  browser storage before upload.

## Server-side validation

Every capture upload is validated in `apps/participation/validation.py` before
a row is written. The client is never the trust boundary.

| Check | Rule | Failure |
|-------|------|---------|
| File size | `0 < size ≤ MAX_CAPTURE_FILE_SIZE` (8 MB default) | `400` |
| Decodability | Pillow must `verify()` then `load()` the bytes | `400` |
| Content type | Taken from the **decoded image format**, not the client's `Content-Type`; must be one of `image/jpeg`, `image/png`, `image/webp` | `400` |
| Dimensions | 100 px ≤ width, height ≤ 8000 px | `400` |
| Integrity | SHA-256 of the bytes stored on the row | — |
| GPS presence | latitude, longitude and accuracy all present | `400` |
| GPS accuracy | `accuracy ≤ MAX_GPS_ACCURACY_METERS` | `400` |
| GPS range | −90 ≤ lat ≤ 90, −180 ≤ lon ≤ 180 | `400` |
| Venue distance | Haversine against the event's coordinates; sets `location_warning` past `VENUE_WARNING_DISTANCE_METERS` | never fails |
| Capture timestamp | Not more than 5 minutes in the future | `400` |
| Event date | Local date of the device timestamp must equal `event.event_date` | `400` |

A missing accuracy value is treated as *"accuracy unknown"* and blocks
submission. It is never treated as perfect accuracy — that distinction is the
difference between a rule and a loophole.

Django's own upload ceilings (`DATA_UPLOAD_MAX_MEMORY_SIZE`,
`FILE_UPLOAD_MAX_MEMORY_SIZE`) are raised to `MAX_CAPTURE_FILE_SIZE + 1 MB` so
that a file just over our limit reaches *our* validator and gets a clear `400`,
instead of being cut off earlier by Django with a vaguer error.

## Storage and retrieval

- The object key is generated server-side:
  `{student_id}/{participation_id}/{version_number}/{uuid4}.{ext}`. The
  client-supplied filename is discarded entirely, which is what makes path
  traversal and storage-key injection impossible rather than merely unlikely.
- `private_capture_storage` is a `FileSystemStorage` with `base_url=None`, so
  no stored object can even produce a URL.
- `MEDIA_URL` is never routed in `config/urls.py`. There is no web path that
  reaches `MEDIA_ROOT`.
- Retrieval is `GET /api/v1/evidence/captures/{id}/image/`, which applies the
  same object-level authorization as the evidence detail endpoint and then
  streams the bytes. Responses are `no-store`.

Swapping to private object storage (S3/GCS/Azure Blob with no public ACL and
server-side-only access) is a change to `apps/participation/storage.py` alone —
that is the reason the abstraction exists. See
[`../deployment/deployment-guide.md`](../deployment/deployment-guide.md#evidence-storage).

## Known limitations

- **The device capture timestamp is client-supplied.** It is bounded against
  implausible future values, but a determined client could report a different
  time. Cryptographic capture attestation is out of scope.
- **GPS coordinates are also client-reported.** Browser geolocation can be
  spoofed by a modified client. Venue distance is therefore a reviewer signal,
  not proof of presence — which is precisely why it warns rather than blocks.
- **The offline queue is unencrypted** (see above).
- These are the reasons a human verifies the evidence. The system's claim is
  that a capture is *harder to fake and easier to review*, not that it is
  tamper-proof.
