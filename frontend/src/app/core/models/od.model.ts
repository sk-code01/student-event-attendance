import { ApprovalStatus, AttendanceEventBrief, PersonBrief } from './attendance.model';

/**
 * An OD (On-Duty) request. Structurally similar to Attendance but a wholly
 * independent academic decision — a participation can have attendance approved
 * and OD rejected, or any other combination. `reason` is the justification the
 * requesting Faculty member supplies for the Event Coordinator to review; `rejection_reason`
 * is the Event Coordinator's reason for refusing.
 */
export interface ODRequest {
  id: number;
  participation: number;
  student: PersonBrief;
  event: AttendanceEventBrief;
  reason: string;
  status: ApprovalStatus;
  requested_by: PersonBrief;
  requested_at: string;
  reviewed_by: PersonBrief | null;
  reviewed_at: string | null;
  rejection_reason: string;
  created_at: string;
  updated_at: string;
}
