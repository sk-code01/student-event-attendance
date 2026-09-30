"""
Object-level permissions for OD — the same convention as
apps.attendance.permissions and apps.verification.permissions. They are kept
as their own classes rather than shared with attendance so that a future
divergence in either workflow's authority model cannot silently change the
other; the two workflows are independent by design.
"""

from rest_framework.permissions import BasePermission


def _in_same_department(user, obj) -> bool:
    """Department scoping with an explicit null guard: a staff user with no
    department must never implicitly match a department-less (Admin-created)
    event's records, which a bare `None == None` comparison would allow."""
    return (
        user.department_id is not None
        and obj.participation.event.department_id == user.department_id
    )


class CanAccessODRequest(BasePermission):
    """Object-level read access: the owning student, Faculty/Event Coordinator scoped to the
    event's department, or Admin/superuser."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role in (user.Role.FACULTY, user.Role.EVENT_COORDINATOR):
            return _in_same_department(user, obj)
        return obj.participation.student_id == user.id


class CanRequestOD(BasePermission):
    """Raising an OD request is a Faculty action, for the same reason
    attendance requests are (see apps.attendance.permissions)."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.is_superuser or user.role == user.Role.FACULTY


class CanReviewODRequest(BasePermission):
    """Approve/reject authority: Event Coordinator scoped to the event's department, or
    Admin/superuser system-wide. Faculty are explicitly excluded."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role != user.Role.EVENT_COORDINATOR:
            return False
        return _in_same_department(user, obj)
