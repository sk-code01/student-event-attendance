from django.db import models


class Department(models.Model):
    """
    A department is a scoping unit for Event Coordinator authority and for Student/Faculty
    association. Business rule: a department may have at most one active Event Coordinator
    (enforced in accounts.User's constraints, since Event Coordinator-ness is a property of
    a User row, not of Department).
    """

    name = models.CharField(max_length=150, unique=True)
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.code} - {self.name}'
