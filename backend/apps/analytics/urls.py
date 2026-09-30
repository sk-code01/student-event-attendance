from django.urls import path

from . import views

urlpatterns = [
    path('overview/', views.OverviewView.as_view(), name='analytics-overview'),
    path('participation/', views.ParticipationView.as_view(), name='analytics-participation'),
    path('events/', views.EventsView.as_view(), name='analytics-events'),
    path('registrations/', views.RegistrationsView.as_view(), name='analytics-registrations'),
    path('attendance/', views.AttendanceView.as_view(), name='analytics-attendance'),
    path('od/', views.ODView.as_view(), name='analytics-od'),
    path('achievements/', views.AchievementsView.as_view(), name='analytics-achievements'),
    path('verification/', views.VerificationView.as_view(), name='analytics-verification'),
    path('trends/', views.TrendsView.as_view(), name='analytics-trends'),
    path('departments/', views.DepartmentsView.as_view(), name='analytics-departments'),
]
