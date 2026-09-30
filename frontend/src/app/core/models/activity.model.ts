import { PersonBrief } from './attendance.model';

/** A row from the existing AuditLog, surfaced either as the caller's own
 * activity feed or (for Event Coordinator/Admin) as the audit trail. */
export interface ActivityRecord {
  id: number;
  actor: PersonBrief | null;
  action: string;
  description: string;
  created_at: string;
}
