import { Role } from './user.model';

/**
 * The shapes returned by the Admin user-management endpoints.
 *
 * These are deliberately separate from `User` (which models
 * `GET /users/me/` — the caller's own identity). An admin row carries
 * moderation fields the self endpoint has no business returning, and keeping
 * them apart stops the self model from quietly growing an `is_superuser`
 * flag that some component then reads as an authorization signal.
 *
 * There is no password field on any of these, by design. The API never sends
 * one, and adding an optional one here would invite a component to try.
 */

/** Department as embedded in an admin user row — enough to render, no more. */
export interface AdminUserDepartment {
  id: number;
  name: string;
  code: string;
}

export interface AdminUser {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: Role;
  /** Students only; null for every other role. */
  university_registration_number: string | null;
  /** Faculty and Event Coordinators; null for every other role. */
  faculty_id: string | null;
  department: AdminUserDepartment | null;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  date_joined: string;
  last_login: string | null;
}

/** The approval history shown on the detail panel. */
export interface AdminUserRegistrationRequest {
  id: number;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  requested_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  rejection_reason: string;
}

export interface AdminUserDetail extends AdminUser {
  first_name: string;
  last_name: string;
  registration_request: AdminUserRegistrationRequest | null;
}

export interface AdminUserStats {
  total: number;
  active: number;
  inactive: number;
  /**
   * Count per role. The API fills this from `User.Role.choices`, so every
   * role is always present with at least 0 — a missing key would be an API
   * bug, not a case the UI needs to defend against.
   */
  by_role: Record<Role, number>;
}

/** Every field is optional: the API takes a partial update and applies only
 * what is sent. `department: null` is meaningful (clear it), which is why the
 * type is `number | null` rather than just `number`. */
export interface AdminUserUpdate {
  email?: string;
  first_name?: string;
  last_name?: string;
  role?: Role;
  department?: number | null;
  is_active?: boolean;
}

export interface AdminUserFilters {
  search?: string;
  role?: string;
  department?: string;
  status?: 'active' | 'inactive' | 'all';
  page?: number;
}

export interface AdminPasswordReset {
  new_password: string;
  confirm_password: string;
}

export interface AdminPasswordResetResult {
  detail: string;
  sessions_revoked: number;
}
