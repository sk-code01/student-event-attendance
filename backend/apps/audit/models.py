from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """
    Minimal audit trail for important state-changing actions (event lifecycle,
    registrations). Deliberately simple — a free-text action code plus a
    human-readable description — rather than a generic-relation object graph,
    since nothing in this phase needs to query "all audit entries for object
    X" programmatically. Extend this model rather than replacing it if a
    later phase needs that.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
        help_text='Who performed the action. Null for system-initiated actions.',
    )
    action = models.CharField(max_length=50)
    description = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['action'])]

    def __str__(self):
        return f'{self.action} by {self.actor_id} at {self.created_at}'

    @classmethod
    def record(cls, *, actor, action, description=''):
        return cls.objects.create(actor=actor, action=action, description=description)
