/** Analytics payloads. Every one is aggregate data computed by the backend —
 * the frontend never derives an authoritative statistic from raw records. */

export interface AnalyticsOverview {
  events: number;
  registrations: number;
  live_registrations: number;
  participations: number;
  evidence_submitted: number;
  verified_participations: number;
  pending_verification: number;
  attendance_requests: number;
  attendance_approved: number;
  od_requests: number;
  od_approved: number;
  achievements: number;
  official_achievements: number;
  /** null when the denominator is zero — rendered as an em dash, never 0%. */
  participation_rate: number | null;
  participation_rate_basis: string;
}

export interface EventBreakdown {
  event_id: number;
  event_title: string;
  participations?: number;
  registrations?: number;
  requests?: number;
  approved?: number;
  achievements?: number;
  submissions?: number;
  verified?: number;
  rejected?: number;
}

export interface CategoryBreakdown {
  category: string;
  participations?: number;
  events?: number;
}

export interface ParticipationAnalytics {
  total_registrations: number;
  live_registrations: number;
  total_participations: number;
  submitted_participations: number;
  draft_participations: number;
  verified_participations: number;
  pending_verification: number;
  rejected_evidence: number;
  resubmission_required: number;
  participation_rate: number | null;
  participation_rate_basis: string;
  verification_success_rate: number | null;
  verification_success_rate_basis: string;
  by_event: EventBreakdown[];
  by_category: CategoryBreakdown[];
}

export interface PerEvent {
  id: number;
  title: string;
  event_date: string;
  category: string;
  status: string;
  registrations: number;
  participations: number;
}

export interface EventAnalytics {
  total_events: number;
  draft_events: number;
  published_events: number;
  cancelled_events: number;
  completed_events: number;
  by_category: CategoryBreakdown[];
  per_event: PerEvent[];
}

export interface RegistrationAnalytics {
  total_registrations: number;
  live_registrations: number;
  cancelled_registrations: number;
  cancellation_rate: number | null;
  cancellation_rate_basis: string;
  by_event: EventBreakdown[];
}

/** Attendance and OD share this shape but remain independent workflows. */
export interface ApprovalAnalytics {
  total_requests: number;
  pending: number;
  approved: number;
  rejected: number;
  approval_rate: number | null;
  approval_rate_basis: string;
  by_event: EventBreakdown[];
}

export interface AchievementTypeBreakdown {
  achievement_type: string;
  achievements: number;
  approved: number;
}

export interface AchievementAnalytics {
  total_achievements: number;
  draft: number;
  pending_approval: number;
  official_achievements: number;
  rejected: number;
  approval_rate: number | null;
  approval_rate_basis: string;
  by_type: AchievementTypeBreakdown[];
  by_event: EventBreakdown[];
}

export interface VerificationAnalytics {
  total_evidence: number;
  pending_review: number;
  verified: number;
  rejected: number;
  resubmission_required: number;
  event_coordinator_overrides: number;
  verification_rate: number | null;
  verification_rate_basis: string;
  decision_basis: string;
  by_event: EventBreakdown[];
}

export interface DepartmentRow {
  department_id: number;
  department: string | null;
  events: number;
  registrations: number;
  participations: number;
  attendance_approved: number;
  od_approved: number;
  official_achievements: number;
}

export interface DepartmentAnalytics {
  departments: DepartmentRow[];
  department_less_events: number;
  department_less_note: string;
}

export type TrendPeriod = 'daily' | 'weekly' | 'monthly';

export interface TrendPoint {
  period: string;
  registrations: number;
  participations: number;
  verified: number;
  attendance_approved: number;
  od_approved: number;
  achievements: number;
}

export interface TrendStatistics {
  total: number;
  periods: number;
  average: number | null;
  latest: number | null;
  previous: number | null;
  change: number | null;
  change_percent: number | null;
  direction: 'rising' | 'falling' | 'steady' | 'insufficient_data';
  moving_average_3: number[];
}

export interface Trends {
  period: TrendPeriod;
  timezone: string;
  series: TrendPoint[];
  statistics: Record<string, TrendStatistics>;
}

/** Filters the UI may send. Every one is re-validated and scope-checked
 * server-side; sending a foreign id produces 403/404, not data. */
export interface AnalyticsFilters {
  date_from?: string;
  date_to?: string;
  event?: number;
  category?: string;
  department?: number;
  student?: number;
  period?: TrendPeriod;
}
