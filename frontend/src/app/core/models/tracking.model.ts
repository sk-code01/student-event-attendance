/**
 * One row of the Event Coordinator's department-wide tracking view: a
 * registered student's position across every stage of the workflow.
 *
 * Every status here is computed by the server at read time and is never
 * stored. `NOT_SUBMITTED` in particular is an observation — the event date
 * passed without a capture — and never implies anything about attendance,
 * which only a coordinator records.
 */

export type LiveCaptureStatus =
  | 'AWAITING_EVENT'
  | 'OPEN_TODAY'
  | 'IN_PROGRESS'
  | 'SUBMITTED'
  | 'NOT_SUBMITTED';

export type TrackingCertificateStatus =
  | 'NOT_ELIGIBLE'
  | 'WINDOW_NOT_OPEN'
  | 'NOT_SUBMITTED'
  | 'SUBMITTED'
  | 'VERIFIED'
  | 'REJECTED'
  | 'ACCEPTED_BY_COORDINATOR';

export type TrackingAttendanceStatus = 'NOT_RECORDED' | 'PENDING' | 'APPROVED' | 'REJECTED';

export interface TrackingRow {
  registration_id: number;
  student: {
    id: number;
    username: string;
    full_name: string;
    university_registration_number: string | null;
    department: string | null;
  };
  event: {
    id: number;
    title: string;
    event_date: string;
    venue: string;
    status: string;
  };

  registration_status: 'REGISTERED' | 'CANCELLED';
  registered_at: string;

  /** Null when the student never captured; the certificate endpoints key on it. */
  participation_id: number | null;
  participation_status: string | null;
  live_capture_status: LiveCaptureStatus;
  live_capture_submitted_at: string | null;
  /** Address where resolved, otherwise coordinates and their accuracy. */
  live_capture_location: string | null;

  verification_status: string;

  certificate_status: TrackingCertificateStatus;
  certificate_attempts_used: number;
  certificate_attempts_remaining: number;

  attendance_status: TrackingAttendanceStatus;
  attendance_is_manual: boolean;
  attendance_decided_by: string | null;
}

/** Server-side filters. Every one narrows; none widens the caller's scope. */
export interface TrackingFilters {
  event?: number | null;
  student?: number | null;
  search?: string;
  registration_status?: string;
  participation_status?: string;
  live_capture_status?: string;
  verification_status?: string;
  certificate_status?: string;
  attendance_status?: string;
}
