export type CaptureRole = 'PRIMARY' | 'ADDITIONAL';
export type EvidenceStatus = 'SUBMITTED' | 'UNDER_REVIEW' | 'VERIFIED' | 'REJECTED' | 'RESUBMISSION_REQUIRED';
export type VerificationDecision = 'VERIFIED' | 'REJECTED' | 'RESUBMISSION_REQUIRED';

export interface EvidenceCapture {
  id: number;
  capture_role: CaptureRole;
  image_url: string;
  mime_type: string;
  file_size: number;
  sha256_hash: string;
  device_capture_timestamp: string;
  server_received_timestamp: string;
  latitude: string;
  longitude: string;
  gps_accuracy: number;
  venue_distance: number | null;
  location_warning: boolean;
  validation_status: string;
  created_at: string;
}

export interface EvidenceVerificationRecord {
  id: number;
  reviewer: { id: number; username: string; role: string };
  decision: VerificationDecision;
  reason: string;
  is_event_coordinator_override: boolean;
  created_at: string;
}

export interface EvidenceVersion {
  id: number;
  version_number: number;
  submitted_by: number;
  submission_reason: string;
  submitted_at: string | null;
  created_at: string;
  captures: EvidenceCapture[];
  has_primary_capture: boolean;
  verifications: EvidenceVerificationRecord[];
  effective_decision: VerificationDecision | null;
  in_progress: boolean;
}

export interface Evidence {
  id: number;
  participation: number;
  student: {
    id: number;
    username: string;
    full_name: string;
    /** The identifier a verifier can check against a register. */
    university_registration_number: string | null;
    email: string;
    department: string | null;
  };
  event: { id: number; title: string; event_date: string; venue: string; category: string; status: string; college: string | null };
  status: EvidenceStatus;
  current_version_number: number | null;
  versions: EvidenceVersion[];
  created_at: string;
  updated_at: string;
}

/** A capture held purely client-side (in memory) before the student
 * confirms final submission — mirrors PendingCapture from participation.model.ts. */
export interface PendingEvidenceCapture {
  role: CaptureRole;
  blob: Blob;
  previewUrl: string;
  deviceCaptureTimestamp: string;
  latitude: number;
  longitude: number;
  gpsAccuracy: number;
}
