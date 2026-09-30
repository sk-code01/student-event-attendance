from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsEventManager(BasePermission):
    """
    Read access is open to any authenticated user (queryset filtering in the
    view handles what each role is allowed to see). Write access requires
    Event Coordinator or Admin at the view level, and — for a specific event — an Event Coordinator may
    only act on events scoped to their own department; Admin/superuser may
    act on any event.
    """

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        user = request.user
        return bool(
            user and user.is_authenticated
            and (user.role in (user.Role.EVENT_COORDINATOR, user.Role.ADMIN) or user.is_superuser)
        )

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        return user.role == user.Role.EVENT_COORDINATOR and obj.department_id == user.department_id
