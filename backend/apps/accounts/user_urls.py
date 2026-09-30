"""Mounted at /api/v1/users/.

Ordering note: the admin user-management detail routes are keyed on
`<int:pk>`, so they can never shadow the named paths above them (`me/`,
`registration-requests/`, `provision-event-coordinator/`) no matter how the list is
reordered. That is deliberate - a `<str:pk>` here would have made the
ordering load-bearing and easy to break later.
"""

from django.urls import path

from .admin_views import (
    AdminUserActivateView,
    AdminUserDeactivateView,
    AdminUserDetailView,
    AdminUserListView,
    AdminUserSetPasswordView,
    AdminUserStatsView,
)
from .views import (
    ChangePasswordView,
    EventCoordinatorProvisionView,
    MeView,
    RegistrationRequestApproveView,
    RegistrationRequestListView,
    RegistrationRequestRejectView,
)

urlpatterns = [
    path('me/', MeView.as_view(), name='user-me'),
    path('me/password/', ChangePasswordView.as_view(), name='user-change-password'),
    path('registration-requests/', RegistrationRequestListView.as_view(), name='registration-request-list'),
    path(
        'registration-requests/<int:pk>/approve/',
        RegistrationRequestApproveView.as_view(),
        name='registration-request-approve',
    ),
    path(
        'registration-requests/<int:pk>/reject/',
        RegistrationRequestRejectView.as_view(),
        name='registration-request-reject',
    ),
    path('provision-event-coordinator/', EventCoordinatorProvisionView.as_view(), name='provision-event-coordinator'),

    # Admin user management (Admin only).
    path('', AdminUserListView.as_view(), name='admin-user-list'),
    path('stats/', AdminUserStatsView.as_view(), name='admin-user-stats'),
    path('<int:pk>/', AdminUserDetailView.as_view(), name='admin-user-detail'),
    path('<int:pk>/activate/', AdminUserActivateView.as_view(), name='admin-user-activate'),
    path('<int:pk>/deactivate/', AdminUserDeactivateView.as_view(), name='admin-user-deactivate'),
    path('<int:pk>/reset-password/', AdminUserSetPasswordView.as_view(), name='admin-user-reset-password'),
]
