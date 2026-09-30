"""
Object-level permissions for attendance, following the convention
established in apps.verification.permissions exactly:

  * Admin/superuser first,
  * then a department-scoped branch for Faculty/Event Coordinator (via `_in_same_department`,
    which compares `obj.participation.event.department_id` to the user's — there
    is still no FacultyEventAssignment table and none is introduced here),
  * then ownership for the student.

A record outside the requester's visible `get_queryset()` resolves to 404 in
the view (never confirming it exists); a visible record with an action that
role may not perform resolves to 403 through these classes.
"""

from rest_framework.permissions import BasePermission


def _event_of(obj):
    """The event an attendance record belongs to.

    Read through the registration, which every record has, rather than through
    the participation, which is null for a student the Event Coordinator marked
    without a live capture.
    """
    if obj.registration_id is not None:
        return obj.registration.event
    return obj.participation.event


def _student_id_of(obj) -> int:
    if obj.registration_id is not None:
        return obj.registration.student_id
    return obj.participation.student_id


def _in_same_department(user, obj) -> bool:
    """Department scoping with an explicit null guard: a staff user with no
    department must never implicitly match a department-less (Admin-created)
    event's records, which a bare `None == None` comparison would allow."""
    return (
        user.department_id is not None
        and _event_of(obj).department_id == user.department_id
    )


class CanAccessAttendance(BasePermission):
    """Object-level read access: the owning student, Faculty/Event Coordinator scoped to the
    event's department, or Admin/superuser."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role in (user.Role.FACULTY, user.Role.EVENT_COORDINATOR):
            return _in_same_department(user, obj)
        return _student_id_of(obj) == user.id


class CanRequestAttendance(BasePermission):
    """Raising an attendance request is a Faculty action. Admin is deliberately
    excluded — exactly as Admin is excluded from `CanVerifyEvidence` in Phase 4
    — because Admin inspects the workflow system-wide rather than impersonating
    the Faculty role inside it. Superusers are allowed as the usual escape
    hatch. The department scope is checked in the view against the target
    participation, since there is no object yet at create time."""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.is_superuser or user.role == user.Role.FACULTY


class CanMarkAttendance(BasePermission):
    """Marking and updating attendance directly is the Event Coordinator's
    responsibility alone.

    Faculty are excluded on purpose and not merely by omission: they request
    attendance and they verify evidence, but they never set the attendance
    record itself. Admin and superusers keep their usual system-wide access.
    """

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return (
            user.is_superuser
            or user.role in (user.Role.EVENT_COORDINATOR, user.Role.ADMIN)
        )


class CanReviewAttendance(BasePermission):
    """Approve/reject authority: Event Coordinator scoped to the event's department, or
    Admin/superuser system-wide. Faculty are explicitly excluded — Faculty
    request attendance, they never approve it."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return True
        if user.role != user.Role.EVENT_COORDINATOR:
            return False
        return _in_same_department(user, obj)
