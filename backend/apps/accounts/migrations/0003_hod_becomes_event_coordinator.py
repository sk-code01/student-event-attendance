"""Renames the HOD role to Event Coordinator.

The role is stored as a string on every User row, so this is a data migration
as well as a schema one. Order matters: the partial unique index that enforces
"one active HOD per department" is dropped first, the rows are rewritten, and
the equivalent index is then created against the new value. Doing it the other
way round would add an index that no existing row matches, silently leaving
the old rows unconstrained.

Reversible on purpose — reverse_code puts the rows and the index back, so a
rollback is a real rollback rather than a one-way door.
"""

from django.db import migrations, models
from django.db.models import Q


def hod_to_event_coordinator(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    RegistrationRequest = apps.get_model('accounts', 'RegistrationRequest')
    User.objects.filter(role='HOD').update(role='EVENT_COORDINATOR')
    # Self-registration never produces HOD requests (a check constraint
    # forbids it), but a historical row would otherwise be left dangling.
    RegistrationRequest.objects.filter(role='HOD').update(role='EVENT_COORDINATOR')


def event_coordinator_to_hod(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    RegistrationRequest = apps.get_model('accounts', 'RegistrationRequest')
    User.objects.filter(role='EVENT_COORDINATOR').update(role='HOD')
    RegistrationRequest.objects.filter(role='EVENT_COORDINATOR').update(role='HOD')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_registrationrequest_alter_user_options_and_more'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='user',
            name='unique_active_hod_per_department',
        ),
        migrations.RunPython(hod_to_event_coordinator, event_coordinator_to_hod),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(
                choices=[
                    ('STUDENT', 'Student'),
                    ('FACULTY', 'Faculty'),
                    ('EVENT_COORDINATOR', 'Event Coordinator'),
                    ('ADMIN', 'Admin'),
                ],
                default='STUDENT',
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='registrationrequest',
            name='role',
            field=models.CharField(
                choices=[
                    ('STUDENT', 'Student'),
                    ('FACULTY', 'Faculty'),
                    ('EVENT_COORDINATOR', 'Event Coordinator'),
                    ('ADMIN', 'Admin'),
                ],
                max_length=20,
            ),
        ),
        migrations.AddConstraint(
            model_name='user',
            constraint=models.UniqueConstraint(
                condition=Q(('is_active', True), ('role', 'EVENT_COORDINATOR')),
                fields=('department',),
                name='unique_active_event_coordinator_per_department',
            ),
        ),
    ]
