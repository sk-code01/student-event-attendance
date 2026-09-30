export type NotificationType =
  | 'REGISTRATION_SUBMITTED' | 'REGISTRATION_APPROVED' | 'REGISTRATION_REJECTED'
  | 'EVENT_PUBLISHED' | 'EVENT_CANCELLED'
  | 'PARTICIPATION_SUBMITTED'
  | 'EVIDENCE_VERIFIED' | 'EVIDENCE_REJECTED' | 'EVIDENCE_RESUBMISSION_REQUIRED'
  | 'EVENT_COORDINATOR_OVERRIDE'
  | 'ATTENDANCE_REQUESTED' | 'ATTENDANCE_APPROVED' | 'ATTENDANCE_REJECTED'
  | 'OD_REQUESTED' | 'OD_APPROVED' | 'OD_REJECTED'
  | 'ACHIEVEMENT_CREATED' | 'ACHIEVEMENT_APPROVED' | 'ACHIEVEMENT_REJECTED';

export type NotificationPriority = 'NORMAL' | 'HIGH';

/**
 * An in-app notification. Distinct from an audit record (the security trail)
 * and from activity (that trail filtered for one user) — a notification is an
 * addressed message with a read state.
 *
 * `action_route` is always an internal Angular path (the backend refuses to
 * store anything else), so it is safe to hand to routerLink.
 */
export interface AppNotification {
  id: number;
  notification_type: NotificationType;
  title: string;
  message: string;
  related_entity_type: string;
  related_entity_id: number | null;
  action_route: string;
  priority: NotificationPriority;
  is_read: boolean;
  read_at: string | null;
  created_at: string;
}
