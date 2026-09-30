from rest_framework.permissions import BasePermission


class CanAccessRegistration(BasePermission):
    """Object-level read/cancel access: the owning student, an Event Coordinator scoped to
    the event's department, or Admin/superuser."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role == user.Role.EVENT_COORDINATOR:
            return obj.event.department_id == user.department_id
        return obj.student_id == user.id
