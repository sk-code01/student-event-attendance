"""
Reusable role-based DRF permissions. These are the actual security boundary
for the API — Angular route guards are UX only and must never be relied on
for authorization.
"""

from rest_framework.permissions import BasePermission


def _has_role(user, *roles):
    if not (user and user.is_authenticated):
        return False
    if user.is_superuser:
        return True
    return user.role in roles


class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return _has_role(request.user, request.user.Role.STUDENT if request.user.is_authenticated else None)


class IsFaculty(BasePermission):
    def has_permission(self, request, view):
        return _has_role(request.user, request.user.Role.FACULTY if request.user.is_authenticated else None)


class IsEventCoordinator(BasePermission):
    def has_permission(self, request, view):
        return _has_role(request.user, request.user.Role.EVENT_COORDINATOR if request.user.is_authenticated else None)


class IsAdminRole(BasePermission):
    """System-wide administrator. Also grants Django superusers, so a
    superuser created without going through the role-provisioning flow is
    never accidentally locked out of admin-only endpoints."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.role == user.Role.ADMIN or user.is_superuser))


class IsEventCoordinatorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated
            and (user.role in (user.Role.EVENT_COORDINATOR, user.Role.ADMIN) or user.is_superuser)
        )


class IsOwnDepartmentEventCoordinator(BasePermission):
    """Object-level check: an Event Coordinator may only act on objects scoped to their own
    department; Admin/superuser bypasses the department scope entirely."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role != user.Role.EVENT_COORDINATOR:
            return False
        obj_department_id = getattr(obj, 'department_id', None)
        return obj_department_id is not None and obj_department_id == user.department_id
