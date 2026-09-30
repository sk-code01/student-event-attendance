import { Routes } from '@angular/router';

import { authGuard } from './core/guards/auth.guard';
import { roleGuard } from './core/guards/role.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'login' },
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'register',
    loadComponent: () => import('./features/auth/register/register.component').then((m) => m.RegisterComponent),
  },
  {
    path: 'unauthorized',
    loadComponent: () =>
      import('./features/auth/unauthorized/unauthorized.component').then((m) => m.UnauthorizedComponent),
  },
  {
    path: 'dashboard',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/dashboard/dashboard.component').then((m) => m.DashboardComponent),
  },
  {
    // The header's profile menu points here. Both entries are real
    // destinations: /profile shows the account, /profile/password opens the
    // same page with the password form as the focus.
    path: 'profile',
    canActivate: [authGuard],
    loadComponent: () => import('./features/profile/profile.component').then((m) => m.ProfileComponent),
  },
  {
    path: 'profile/password',
    canActivate: [authGuard],
    loadComponent: () => import('./features/profile/profile.component').then((m) => m.ProfileComponent),
  },
  {
    path: 'analytics',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/analytics/analytics-page.component').then((m) => m.AnalyticsPageComponent),
  },
  {
    path: 'reports',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/reports/reports-page.component').then((m) => m.ReportsPageComponent),
  },
  {
    // AI decision support (Phase 8). Recommendations are personal to a
    // student's own history; the API answers 403 for staff regardless.
    path: 'recommendations',
    canActivate: [authGuard, roleGuard('STUDENT')],
    loadComponent: () =>
      import('./features/ai/recommendations/recommendations.component').then((m) => m.RecommendationsComponent),
  },
  {
    // Every role: the backend decides whether the caller gets their own
    // label, a distribution, or per-student rows.
    path: 'engagement',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/ai/engagement/engagement.component').then((m) => m.EngagementComponent),
  },
  {
    // Reviewer view. The guard is UX only -- the backend scopes the rows by
    // department for Faculty/Event Coordinator and would return a student only their own.
    path: 'anomalies',
    canActivate: [authGuard, roleGuard('FACULTY', 'EVENT_COORDINATOR', 'ADMIN')],
    loadComponent: () =>
      import('./features/ai/anomalies/anomalies.component').then((m) => m.AnomaliesComponent),
  },
  {
    path: 'notifications',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/notifications/notifications-page.component').then(
        (m) => m.NotificationsPageComponent,
      ),
  },
  {
    // Guarded for Event Coordinator and Admin. The guard is UX only -- the backend refuses
    // Student/Faculty with 403 regardless of what the router allows.
    path: 'audit',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR', 'ADMIN')],
    loadComponent: () => import('./features/audit/audit-log.component').then((m) => m.AuditLogComponent),
  },
  {
    path: 'student',
    canActivate: [authGuard, roleGuard('STUDENT')],
    loadComponent: () =>
      import('./features/student/student-shell.component').then((m) => m.StudentShellComponent),
  },
  {
    path: 'student/events',
    canActivate: [authGuard, roleGuard('STUDENT')],
    loadComponent: () => import('./features/events/pages/event-list/event-list.component').then((m) => m.EventListComponent),
  },
  {
    path: 'student/events/:id',
    canActivate: [authGuard, roleGuard('STUDENT')],
    loadComponent: () =>
      import('./features/events/pages/event-detail/event-detail.component').then((m) => m.EventDetailComponent),
  },
  {
    path: 'student/registrations',
    canActivate: [authGuard, roleGuard('STUDENT')],
    loadComponent: () =>
      import('./features/events/pages/my-registrations/my-registrations.component').then(
        (m) => m.MyRegistrationsComponent,
      ),
  },
  {
    path: 'student/events/:id/participate',
    canActivate: [authGuard, roleGuard('STUDENT')],
    loadComponent: () =>
      import('./features/participation/live-capture/live-capture.component').then((m) => m.LiveCaptureComponent),
  },
  {
    path: 'student/participation',
    canActivate: [authGuard, roleGuard('STUDENT')],
    loadComponent: () =>
      import('./features/participation/history/participation-history.component').then(
        (m) => m.ParticipationHistoryComponent,
      ),
  },
  {
    path: 'student/participation/:id/resubmit',
    canActivate: [authGuard, roleGuard('STUDENT')],
    data: { mode: 'resubmit' },
    loadComponent: () =>
      import('./features/participation/live-capture/live-capture.component').then((m) => m.LiveCaptureComponent),
  },
  {
    path: 'student/attendance',
    canActivate: [authGuard, roleGuard('STUDENT')],
    loadComponent: () =>
      import('./features/student/attendance/student-attendance.component').then(
        (m) => m.StudentAttendanceComponent,
      ),
  },
  {
    path: 'student/od',
    canActivate: [authGuard, roleGuard('STUDENT')],
    loadComponent: () =>
      import('./features/student/od/student-od.component').then((m) => m.StudentOdComponent),
  },
  {
    path: 'student/achievements',
    canActivate: [authGuard, roleGuard('STUDENT')],
    loadComponent: () =>
      import('./features/student/achievements/student-achievements.component').then(
        (m) => m.StudentAchievementsComponent,
      ),
  },
  {
    path: 'faculty/verification',
    canActivate: [authGuard, roleGuard('FACULTY')],
    loadComponent: () =>
      import('./features/faculty/verification/queue/verification-queue.component').then(
        (m) => m.VerificationQueueComponent,
      ),
  },
  {
    path: 'faculty/verification/:id',
    canActivate: [authGuard, roleGuard('FACULTY')],
    loadComponent: () =>
      import('./features/faculty/verification/detail/verification-detail.component').then(
        (m) => m.VerificationDetailComponent,
      ),
  },
  {
    path: 'faculty/attendance-requests',
    canActivate: [authGuard, roleGuard('FACULTY')],
    loadComponent: () =>
      import('./features/faculty/requests/faculty-attendance-requests.component').then(
        (m) => m.FacultyAttendanceRequestsComponent,
      ),
  },
  {
    path: 'faculty/od-requests',
    canActivate: [authGuard, roleGuard('FACULTY')],
    loadComponent: () =>
      import('./features/faculty/requests/faculty-od-requests.component').then(
        (m) => m.FacultyOdRequestsComponent,
      ),
  },
  {
    path: 'faculty/achievements',
    canActivate: [authGuard, roleGuard('FACULTY')],
    loadComponent: () =>
      import('./features/faculty/achievements/faculty-achievements.component').then(
        (m) => m.FacultyAchievementsComponent,
      ),
  },
  {
    path: 'event-coordinator/verification',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () =>
      import('./features/event-coordinator/verification/event-coordinator-verification-list.component').then(
        (m) => m.EventCoordinatorVerificationListComponent,
      ),
  },
  {
    path: 'event-coordinator/verification/:id',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () =>
      import('./features/event-coordinator/verification/event-coordinator-verification-detail.component').then(
        (m) => m.EventCoordinatorVerificationDetailComponent,
      ),
  },
  {
    path: 'faculty',
    canActivate: [authGuard, roleGuard('FACULTY')],
    loadComponent: () =>
      import('./features/faculty/faculty-shell.component').then((m) => m.FacultyShellComponent),
  },
  {
    path: 'faculty/events',
    canActivate: [authGuard, roleGuard('FACULTY')],
    loadComponent: () => import('./features/events/pages/event-list/event-list.component').then((m) => m.EventListComponent),
  },
  {
    path: 'event-coordinator',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () => import('./features/event-coordinator/event-coordinator-shell.component').then((m) => m.EventCoordinatorShellComponent),
  },
  {
    path: 'event-coordinator/events',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () =>
      import('./features/events/pages/event-list/event-management-list.component').then(
        (m) => m.EventManagementListComponent,
      ),
  },
  {
    path: 'event-coordinator/events/new',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () => import('./features/events/pages/event-form/event-form.component').then((m) => m.EventFormComponent),
  },
  {
    path: 'event-coordinator/events/:id/edit',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () => import('./features/events/pages/event-form/event-form.component').then((m) => m.EventFormComponent),
  },
  {
    path: 'event-coordinator/events/:id/registrations',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () =>
      import('./features/events/pages/event-registrations/event-registrations.component').then(
        (m) => m.EventRegistrationsComponent,
      ),
  },
  {
    path: 'student/certificates',
    canActivate: [authGuard, roleGuard('STUDENT')],
    loadComponent: () =>
      import('./features/certificates/my-certificates.component').then((m) => m.MyCertificatesComponent),
  },
  {
    path: 'faculty/certificates',
    canActivate: [authGuard, roleGuard('FACULTY')],
    loadComponent: () =>
      import('./features/certificates/certificate-review.component').then((m) => m.CertificateReviewComponent),
  },
  {
    path: 'event-coordinator/certificates',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () =>
      import('./features/certificates/certificate-review.component').then((m) => m.CertificateReviewComponent),
  },
  {
    path: 'event-coordinator/tracking',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () =>
      import('./features/event-coordinator/tracking/event-coordinator-tracking.component').then(
        (m) => m.EventCoordinatorTrackingComponent,
      ),
  },
  {
    path: 'event-coordinator/attendance',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () =>
      import('./features/event-coordinator/attendance/event-coordinator-attendance.component').then((m) => m.EventCoordinatorAttendanceComponent),
  },
  {
    path: 'event-coordinator/od',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () => import('./features/event-coordinator/od/event-coordinator-od.component').then((m) => m.EventCoordinatorOdComponent),
  },
  {
    path: 'event-coordinator/achievements',
    canActivate: [authGuard, roleGuard('EVENT_COORDINATOR')],
    loadComponent: () =>
      import('./features/event-coordinator/achievements/event-coordinator-achievements.component').then((m) => m.EventCoordinatorAchievementsComponent),
  },
  {
    path: 'admin',
    canActivate: [authGuard, roleGuard('ADMIN')],
    loadComponent: () => import('./features/admin/admin-shell.component').then((m) => m.AdminShellComponent),
  },
  {
    // Admin user management. The guard keeps the link out of other roles'
    // navigation; every endpoint the page calls independently refuses a
    // non-Admin with 403, so the guard is UX and not the boundary.
    path: 'admin/users',
    canActivate: [authGuard, roleGuard('ADMIN')],
    loadComponent: () =>
      import('./features/admin/users/user-management.component').then((m) => m.UserManagementComponent),
  },
  {
    path: 'admin/colleges',
    canActivate: [authGuard, roleGuard('ADMIN')],
    loadComponent: () =>
      import('./features/admin/colleges/college-management.component').then((m) => m.CollegeManagementComponent),
  },
  {
    path: 'admin/events',
    canActivate: [authGuard, roleGuard('ADMIN')],
    loadComponent: () =>
      import('./features/events/pages/event-list/event-management-list.component').then(
        (m) => m.EventManagementListComponent,
      ),
  },
  {
    path: 'admin/events/new',
    canActivate: [authGuard, roleGuard('ADMIN')],
    loadComponent: () => import('./features/events/pages/event-form/event-form.component').then((m) => m.EventFormComponent),
  },
  {
    path: 'admin/events/:id/edit',
    canActivate: [authGuard, roleGuard('ADMIN')],
    loadComponent: () => import('./features/events/pages/event-form/event-form.component').then((m) => m.EventFormComponent),
  },
  {
    path: 'admin/events/:id/registrations',
    canActivate: [authGuard, roleGuard('ADMIN')],
    loadComponent: () =>
      import('./features/events/pages/event-registrations/event-registrations.component').then(
        (m) => m.EventRegistrationsComponent,
      ),
  },
  {
    path: 'admin/attendance',
    canActivate: [authGuard, roleGuard('ADMIN')],
    loadComponent: () =>
      import('./features/admin/oversight/admin-attendance.component').then((m) => m.AdminAttendanceComponent),
  },
  {
    path: 'admin/od',
    canActivate: [authGuard, roleGuard('ADMIN')],
    loadComponent: () =>
      import('./features/admin/oversight/admin-od.component').then((m) => m.AdminOdComponent),
  },
  {
    path: 'admin/achievements',
    canActivate: [authGuard, roleGuard('ADMIN')],
    loadComponent: () =>
      import('./features/admin/oversight/admin-achievements.component').then(
        (m) => m.AdminAchievementsComponent,
      ),
  },
  { path: '**', redirectTo: 'login' },
];
