from django.db import models


class College(models.Model):
    """
    The institution conducting an event. Distinct from Department (the
    institution's internal academic-structure unit used for Event Coordinator/Student/
    Faculty scoping) — an event's conducting college is about *where/which
    institution* is running the event, not who administratively owns it.
    """

    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.code} - {self.name}'
