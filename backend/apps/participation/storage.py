"""
Private storage abstraction for participation evidence.

This project does not yet integrate a cloud object store (S3/GCS/Azure
Blob). Rather than build that integration prematurely, this module gives
Phase 4 (and any future phase) a single place to swap the backing storage
without touching model/view code: everything that stores or serves a
capture image goes through `private_capture_storage`.

Today it is a `FileSystemStorage` rooted at `MEDIA_ROOT/participation_captures/`.
Two things make this safe for evidence data despite living under
`MEDIA_ROOT`:

1. `config/urls.py` never wires up Django's static media-serving helper for
   `MEDIA_URL`, so nothing under `MEDIA_ROOT` is served directly by the
   webserver — there is no public URL for a stored capture.
2. The only way to read a capture's bytes back out is the authenticated,
   authorized `GET /api/v1/evidence/captures/{id}/image/` view (see
   `EvidenceCaptureImageView` in apps/verification/views.py), which streams
   the file after an object-level permission check. The stored object key and
   `FieldFile.url` are never returned to clients — serializers expose only
   that API path.

Object keys are always server-generated (see `capture_upload_path` in
models.py) — a client-supplied filename is never used as, or incorporated
into, a storage path, which rules out path traversal and storage-key
injection via the upload filename.
"""

from django.conf import settings
from django.core.files.storage import FileSystemStorage

private_capture_storage = FileSystemStorage(
    location=str(settings.MEDIA_ROOT / 'participation_captures'),
    base_url=None,  # deliberate: never generate a public URL for this storage
)
