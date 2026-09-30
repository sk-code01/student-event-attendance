/**
 * Attendance and OD share this status set but are separate records in
 * separate backend apps — never treat one as a status of the other.
 */
export type ApprovalStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export interface PersonBrief {
  id: number;
  username: string;
  role: string;
  department?: string | null;
}

export interface AttendanceEventBrief {
  id: number;
  title: string;
  event_date: string;
  venue: string;
}

export interface Attendance {
  id: number;
  /** Null when the student never submitted a live capture — the case the
   *  Event Coordinator marks manually. */
  participation: number | null;
  /** The registration this attendance belongs to; every record has one. */
  registration: number;
  student: PersonBrief;
  event: AttendanceEventBrief;
  status: ApprovalStatus;
  /** True when the coordinator recorded it directly rather than deciding a
   *  Faculty request. Attendance is never inferred from a registration. */
  is_manual: boolean;
  /** Null for a manually marked record, which has no requester. */
  requested_by: PersonBrief | null;
  requested_at: string;
  reviewed_by: PersonBrief | null;
  reviewed_at: string | null;
  rejection_reason: string;
  created_at: string;
  updated_at: string;
}
