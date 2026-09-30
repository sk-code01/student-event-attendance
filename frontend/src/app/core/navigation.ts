import { Role } from './models/user.model';

export interface NavItem {
  label: string;
  route: string;
  /** Key into the icon set rendered by the sidebar. */
  icon: string;
  /** Exact match only — used for section roots like /admin that would
   *  otherwise stay highlighted on every child route. */
  exact?: boolean;
}

export interface NavSection {
  label: string;
  items: NavItem[];
}

/**
 * Per-role navigation.
 *
 * This decides what each role *sees*, and nothing more. It is not an
 * authorization boundary: every route also carries `roleGuard`, and every
 * endpoint behind it independently refuses the wrong role. Hiding a link the
 * backend would refuse is a courtesy, not a control.
 *
 * Section ordering is where the four roles' priorities show. Faculty lead
 * with their verification queue because that is their job; Students lead
 * with discovery; Event Coordinators lead with approvals; Admin leads with the system.
 * Every route below exists in `app.routes.ts`.
 */
export const NAVIGATION: Record<Role, NavSection[]> = {
  ADMIN: [
    {
      label: 'Overview',
      items: [
        { label: 'Dashboard', route: '/dashboard', icon: 'grid' },
        { label: 'Admin Area', route: '/admin', icon: 'sliders', exact: true },
      ],
    },
    {
      label: 'System Management',
      items: [
        { label: 'Users', route: '/admin/users', icon: 'users' },
        { label: 'Colleges', route: '/admin/colleges', icon: 'building' },
        { label: 'Events', route: '/admin/events', icon: 'calendar' },
      ],
    },
    {
      label: 'Oversight',
      items: [
        { label: 'Attendance', route: '/admin/attendance', icon: 'clipboard' },
        { label: 'On-Duty', route: '/admin/od', icon: 'route' },
        { label: 'Achievements', route: '/admin/achievements', icon: 'trophy' },
        { label: 'Audit Log', route: '/audit', icon: 'shield' },
      ],
    },
    {
      label: 'Intelligence',
      items: [
        { label: 'Analytics', route: '/analytics', icon: 'chart' },
        { label: 'Reports', route: '/reports', icon: 'document' },
        { label: 'Risk Signals', route: '/anomalies', icon: 'pulse' },
        { label: 'Engagement', route: '/engagement', icon: 'spark' },
      ],
    },
  ],

  EVENT_COORDINATOR: [
    {
      label: 'Overview',
      items: [
        { label: 'Dashboard', route: '/dashboard', icon: 'grid' },
        { label: 'Department', route: '/event-coordinator', icon: 'building', exact: true },
        { label: 'Student Tracking', route: '/event-coordinator/tracking', icon: 'users' },
      ],
    },
    {
      label: 'Approvals',
      items: [
        { label: 'Verification', route: '/event-coordinator/verification', icon: 'check-shield' },
        { label: 'Attendance', route: '/event-coordinator/attendance', icon: 'clipboard' },
        { label: 'On-Duty', route: '/event-coordinator/od', icon: 'route' },
        { label: 'Achievements', route: '/event-coordinator/achievements', icon: 'trophy' },
        { label: 'Certificates', route: '/event-coordinator/certificates', icon: 'document' },
      ],
    },
    {
      label: 'Events',
      items: [{ label: 'Manage Events', route: '/event-coordinator/events', icon: 'calendar' }],
    },
    {
      label: 'Insight',
      items: [
        { label: 'Analytics', route: '/analytics', icon: 'chart' },
        { label: 'Reports', route: '/reports', icon: 'document' },
        { label: 'Risk Signals', route: '/anomalies', icon: 'pulse' },
        { label: 'Engagement', route: '/engagement', icon: 'spark' },
        { label: 'Audit Log', route: '/audit', icon: 'shield' },
      ],
    },
  ],

  FACULTY: [
    {
      label: 'Workspace',
      items: [
        { label: 'Dashboard', route: '/dashboard', icon: 'grid' },
        { label: 'My Area', route: '/faculty', icon: 'briefcase', exact: true },
      ],
    },
    {
      label: 'Tasks',
      items: [
        { label: 'Verification Queue', route: '/faculty/verification', icon: 'check-shield' },
        { label: 'Certificates', route: '/faculty/certificates', icon: 'document' },
        { label: 'Attendance Requests', route: '/faculty/attendance-requests', icon: 'clipboard' },
        { label: 'OD Requests', route: '/faculty/od-requests', icon: 'route' },
        { label: 'Achievements', route: '/faculty/achievements', icon: 'trophy' },
      ],
    },
    {
      label: 'Reference',
      items: [
        { label: 'Events', route: '/faculty/events', icon: 'calendar' },
        { label: 'Analytics', route: '/analytics', icon: 'chart' },
        { label: 'Reports', route: '/reports', icon: 'document' },
        { label: 'Risk Signals', route: '/anomalies', icon: 'pulse' },
        { label: 'Engagement', route: '/engagement', icon: 'spark' },
      ],
    },
  ],

  STUDENT: [
    {
      label: 'Discover',
      items: [
        { label: 'Dashboard', route: '/dashboard', icon: 'grid' },
        { label: 'Browse Events', route: '/student/events', icon: 'calendar' },
        { label: 'Recommended', route: '/recommendations', icon: 'spark' },
      ],
    },
    {
      label: 'My Activity',
      items: [
        { label: 'My Registrations', route: '/student/registrations', icon: 'bookmark' },
        { label: 'My Participation', route: '/student/participation', icon: 'camera' },
        { label: 'My Certificates', route: '/student/certificates', icon: 'document' },
        { label: 'My Attendance', route: '/student/attendance', icon: 'clipboard' },
        { label: 'My OD Requests', route: '/student/od', icon: 'route' },
        { label: 'My Achievements', route: '/student/achievements', icon: 'trophy' },
      ],
    },
    {
      label: 'Progress',
      items: [
        { label: 'My Analytics', route: '/analytics', icon: 'chart' },
        { label: 'Engagement', route: '/engagement', icon: 'pulse' },
        { label: 'Reports', route: '/reports', icon: 'document' },
      ],
    },
  ],
};

/** Human-readable role label for the sidebar and header. */
export const ROLE_LABEL: Record<Role, string> = {
  ADMIN: 'Administrator',
  EVENT_COORDINATOR: 'Event Coordinator',
  FACULTY: 'Faculty',
  STUDENT: 'Student',
};

/** Where each role's "home" area lives, used after login and by the shell. */
export const ROLE_HOME: Record<Role, string> = {
  ADMIN: '/admin',
  EVENT_COORDINATOR: '/event-coordinator',
  FACULTY: '/faculty',
  STUDENT: '/student',
};
