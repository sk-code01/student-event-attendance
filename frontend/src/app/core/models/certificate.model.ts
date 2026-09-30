import { PersonBrief } from './attendance.model';

/** The Faculty-facing state of a certificate submission. */
export type CertificateStatus =
  | 'SUBMITTED'
  | 'VERIFIED'
  | 'REJECTED'
  | 'ACCEPTED_BY_COORDINATOR';

/**
 * The Event Coordinator's final decision, which sits *after* Faculty
 * verification rather than replacing it — both remain readable on the record.
 */
export type CertificateFinalDecision = 'ACCEPTED' | 'REJECTED' | '';

export interface Certificate {
  id: number;
  participation: number;
  /** 1-based, server-derived. Three are allowed in total. */
  attempt_number: number;
  status: CertificateStatus;

  original_filename: string;
  mime_type: string;
  file_size: number;

  student: PersonBrief;
  event: { id: number; title: string; event_date: string };
  submitted_at: string;

  reviewed_by: PersonBrief | null;
  reviewed_at: string | null;
  rejection_reason: string;

  final_decision: CertificateFinalDecision;
  final_decided_by: PersonBrief | null;
  final_decided_at: string | null;
  final_rejection_reason: string;
  /** Faculty have verified it and the coordinator has not yet decided. */
  awaits_final_decision: boolean;

  /** The authenticated download path. The storage location is never exposed. */
  download_url: string;
  attempts_used: number;
  attempts_remaining: number;
}

/**
 * Whether the student may upload right now, and why not when they cannot —
 * the reason matters, because "closed" has several quite different causes.
 */
export interface CertificateEligibility {
  can_upload: boolean;
  reason: string | null;
  window_opens_on: string | null;
  attempts_used: number;
  attempts_remaining: number;
  max_attempts: number;
}
