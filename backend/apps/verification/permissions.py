from rest_framework.permissions import BasePermission


class CanAccessEvidence(BasePermission):
    """Object-level read access: the owning student, Faculty/Event Coordinator scoped to
    the event's department, or Admin/superuser. Mirrors
    apps.participation.permissions.CanAccessParticipation's convention —
    an object outside the requester's visible queryset resolves to 404
    (via get_queryset filtering on the view), this only guards the
    remaining in-queryset edge cases."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role in (user.Role.FACULTY, user.Role.EVENT_COORDINATOR):
            return obj.participation.event.department_id == user.department_id
        return obj.participation.student_id == user.id


class CanVerifyEvidence(BasePermission):
    """Write access for the verify/reject/request-resubmission decision
    actions: Faculty scoped to the event's department, or a superuser.
    Admin is deliberately excluded from making Faculty-role decisions
    (Admin can inspect, not impersonate Faculty/Event Coordinator)."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True
        if user.role != user.Role.FACULTY:
            return False
        return obj.participation.event.department_id == user.department_id


class CanOverrideVerification(BasePermission):
    """Write access for the Event Coordinator override action: Event Coordinator scoped to the event's
    department, or Admin/superuser system-wide."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role != user.Role.EVENT_COORDINATOR:
            return False
        return obj.participation.event.department_id == user.department_id
