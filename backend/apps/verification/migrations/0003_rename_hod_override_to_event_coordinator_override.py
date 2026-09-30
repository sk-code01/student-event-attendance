"""Renames EvidenceVerification.is_hod_override for the Event Coordinator role.

`RenameField` rather than remove-and-add: the column carries the record of
which decisions were overrides, and dropping it would destroy that history.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('verification', '0002_migrate_participation_captures'),
    ]

    operations = [
        migrations.RenameField(
            model_name='evidenceverification',
            old_name='is_hod_override',
            new_name='is_event_coordinator_override',
        ),
    ]
