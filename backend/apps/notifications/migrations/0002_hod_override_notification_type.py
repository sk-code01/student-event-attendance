"""Renames the HOD_OVERRIDE notification type to EVENT_COORDINATOR_OVERRIDE.

Notifications are a permanent record the user can still open, so existing rows
are rewritten rather than left pointing at a type the code no longer knows —
an unknown type would render with no label.
"""

from django.db import migrations, models


def rename_type(apps, schema_editor):
    Notification = apps.get_model('notifications', 'Notification')
    Notification.objects.filter(notification_type='HOD_OVERRIDE').update(
        notification_type='EVENT_COORDINATOR_OVERRIDE',
    )


def restore_type(apps, schema_editor):
    Notification = apps.get_model('notifications', 'Notification')
    Notification.objects.filter(notification_type='EVENT_COORDINATOR_OVERRIDE').update(
        notification_type='HOD_OVERRIDE',
    )


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(rename_type, restore_type),
    ]
