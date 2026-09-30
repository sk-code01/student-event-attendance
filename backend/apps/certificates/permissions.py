"""
Object-level rules for certificates.

The same convention as the rest of the project: the view's queryset does the
scoping so an out-of-scope id is a 404 rather than a 403, and these classes
guard the remaining in-queryset cases. Department scope is taken from the
event, which is what ties a record to the coordinator and faculty who may
act on it.
"""

from rest_framework.permissions import BasePermission


class CanAccessCertificate(BasePermission):
    """Read access: the owning student, Faculty or the Event Coordinator of
    the event's department, or Admin/superuser."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role in (user.Role.FACULTY, user.Role.EVENT_COORDINATOR):
            return obj.participation.event.department_id == user.department_id
        return obj.participation.student_id == user.id


class CanVerifyCertificate(BasePermission):
    """Write access for the verify/reject decision: Faculty scoped to the
    event's department, or a superuser.

    Admin is excluded for the same reason it is excluded from verifying
    evidence — Admin inspects, it does not stand in for Faculty. The Event
    Coordinator is excluded here too: their power over a certificate is the
    narrow post-exhaustion acceptance below, not ordinary verification.
    """

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        if user.role != user.Role.FACULTY:
            return False
        return obj.participation.event.department_id == user.department_id


class CanAcceptExhaustedCertificate(BasePermission):
    """Write access for accepting a rejected certificate once the attempts are
    used up: the Event Coordinator of the event's department, or
    Admin/superuser."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role != user.Role.EVENT_COORDINATOR:
            return False
        return obj.participation.event.department_id == user.department_id
