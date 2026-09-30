import { AttendanceEventBrief, PersonBrief } from './attendance.model';

export type AchievementStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED';

/** Only an APPROVED achievement is official — `is_official` is computed
 * server-side so the UI never has to re-derive that rule. */
export interface Achievement {
  id: number;
  participation: number;
  student: PersonBrief;
  event: AttendanceEventBrief;
  title: string;
  description: string;
  achievement_type: string;
  achievement_date: string;
  status: AchievementStatus;
  is_official: boolean;
  created_by: PersonBrief;
  reviewed_by: PersonBrief | null;
  reviewed_at: string | null;
  rejection_reason: string;
  created_at: string;
  updated_at: string;
}

export interface AchievementCreatePayload {
  participation: number;
  title: string;
  description?: string;
  achievement_type: string;
  achievement_date: string;
  submit_for_approval?: boolean;
}

export type AchievementUpdatePayload = Partial<
  Pick<Achievement, 'title' | 'description' | 'achievement_type' | 'achievement_date'>
>;
