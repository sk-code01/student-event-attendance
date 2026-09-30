"""
Object-level permissions for achievements — same convention as
apps.attendance/od/verification, with one extra role in the write path:
unlike attendance and OD (Faculty-requested only), an Event Coordinator/Admin may also
create an achievement directly, and theirs is authoritative on creation.
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


class CanAccessAchievement(BasePermission):
    """Object-level read access: the owning student, Faculty/Event Coordinator scoped to the
    event's department, or Admin/superuser. Students additionally never see
    another student's records because of the queryset filter in the view."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role in (user.Role.FACULTY, user.Role.EVENT_COORDINATOR):
            return _in_same_department(user, obj)
        return obj.participation.student_id == user.id


class CanCreateAchievement(BasePermission):
    """Faculty (record goes to DRAFT/PENDING_APPROVAL) and Event Coordinator/Admin (record is
    authoritative immediately) may create. Students may never create an
    achievement for themselves or anyone else — official academic records are
    authored by staff only. Department scope is checked in the view against the
    target participation, since there is no object yet at create time."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.is_superuser or user.role in (user.Role.FACULTY, user.Role.EVENT_COORDINATOR, user.Role.ADMIN)


class CanEditAchievement(BasePermission):
    """Edit/submit-for-approval access. Creator-only and draft-only are both
    enforced in the service layer; this class is the role/department gate in
    front of it, and is what keeps students out entirely."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role not in (user.Role.FACULTY, user.Role.EVENT_COORDINATOR):
            return False
        return _in_same_department(user, obj)


class CanReviewAchievement(BasePermission):
    """Approve/reject authority: Event Coordinator scoped to the event's department, or
    Admin/superuser system-wide. Faculty create achievements; they never
    approve them, not even their own."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role != user.Role.EVENT_COORDINATOR:
            return False
        return _in_same_department(user, obj)
