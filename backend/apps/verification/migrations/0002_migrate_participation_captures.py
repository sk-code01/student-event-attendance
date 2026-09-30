"""
Data migration: converts every existing Phase 3 `ParticipationCapture` row
into the Phase 4 `Evidence` / `EvidenceVersion(version_number=1)` /
`EvidenceCapture` structure, preserving every field (hash, timestamps, GPS,
and the stored file reference itself — `object_reference` is set to the
same relative path `ParticipationCapture.image` already pointed at, on the
same underlying storage, so no file bytes are copied or re-uploaded).

Must run AFTER apps.verification.0001_initial (so the new tables exist) and
apps.participation.0002 (so `Participation.status`/`verified_at` are in
their final Phase 4 shape), and BEFORE
apps.participation.0003_delete_participationcapture (so the source table is
still there to read) — see that migration's dependency on this one.
"""

from django.db import migrations


def migrate_captures(apps, schema_editor):
    ParticipationCapture = apps.get_model('participation', 'ParticipationCapture')
    Evidence = apps.get_model('verification', 'Evidence')
    EvidenceVersion = apps.get_model('verification', 'EvidenceVersion')
    EvidenceCapture = apps.get_model('verification', 'EvidenceCapture')

    captures_by_participation = {}
    for capture in ParticipationCapture.objects.select_related('participation').order_by('created_at'):
        captures_by_participation.setdefault(capture.participation_id, []).append(capture)

    for participation_id, captures in captures_by_participation.items():
        participation = captures[0].participation
        evidence = Evidence.objects.create(participation_id=participation_id, status='SUBMITTED')

        version = EvidenceVersion.objects.create(
            evidence=evidence,
            version_number=1,
            submitted_by_id=participation.student_id,
            submitted_at=participation.submitted_at,
        )
        for capture in captures:
            EvidenceCapture.objects.create(
                evidence_version=version,
                capture_role=capture.role,
                object_reference=capture.image.name,
                mime_type=capture.mime_type,
                file_size=capture.file_size,
                sha256_hash=capture.sha256_hash,
                device_capture_timestamp=capture.device_capture_timestamp,
                server_received_timestamp=capture.server_received_timestamp,
                latitude=capture.latitude,
                longitude=capture.longitude,
                gps_accuracy=capture.gps_accuracy,
                venue_distance=capture.venue_distance,
                location_warning=capture.location_warning,
                validation_status='VALID',
            )

        if participation.submitted_at is not None:
            evidence.current_version = version
            evidence.save(update_fields=['current_version'])
        # else: a DRAFT participation with a stray, never-submitted capture
        # (e.g. an old retry after a rejected upload) — the capture is still
        # preserved above, but the version is left unsubmitted and
        # current_version unset, exactly as the live open/submit flow would.


def reverse_noop(apps, schema_editor):
    # Irreversible in practice — reversing would mean reconstructing
    # ParticipationCapture rows one-for-one. The created Evidence rows are
    # simply left in place if this migration is ever rolled back.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('verification', '0001_initial'),
        ('participation', '0002_remove_participation_verified_at_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_captures, reverse_noop),
    ]
