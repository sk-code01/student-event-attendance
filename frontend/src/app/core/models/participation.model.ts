export type CaptureRole = 'PRIMARY' | 'ADDITIONAL';
export type ParticipationStatus = 'DRAFT' | 'SUBMITTED';

export interface Participation {
  id: number;
  registration: number;
  student: { id: number; username: string; email: string };
  event: { id: number; title: string; event_date: string; venue: string; status: string };
  status: ParticipationStatus;
  evidence_id: number | null;
  evidence_status: string | null;
  submitted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EligibilityResult {
  eligible: boolean;
  reason: string | null;
  max_gps_accuracy_meters: number;
}

/** A capture held purely client-side (in memory) before the student
 * confirms final submission — never uploaded per-retake, only once the
 * student accepts it into the review list. */
export interface PendingCapture {
  role: CaptureRole;
  blob: Blob;
  previewUrl: string;
  deviceCaptureTimestamp: string;
  latitude: number;
  longitude: number;
  gpsAccuracy: number;
}
