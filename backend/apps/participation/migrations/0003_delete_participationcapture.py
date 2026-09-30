# Deletes ParticipationCapture only after apps.verification.0002 has copied
# every row into Evidence/EvidenceVersion/EvidenceCapture (see that
# migration's docstring for why the split from 0002 was necessary).

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('participation', '0002_remove_participation_verified_at_and_more'),
        ('verification', '0002_migrate_participation_captures'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ParticipationCapture',
        ),
    ]
