import { Role, User } from './user.model';

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenPair {
  access: string;
  refresh: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  /** Required for every role. The institution records one full name, not a
   *  first/last pair. */
  full_name: string;
  password: string;
  confirm_password: string;
  /** Admin is never self-registered; the API rejects it at field level. */
  role: Extract<Role, 'STUDENT' | 'FACULTY' | 'EVENT_COORDINATOR'>;
  department: number;
  /** Student only. A USN, UUCMS number or university registration number —
   *  no single format is assumed. */
  university_registration_number?: string;
  /** Faculty only. The identifier issued by the college. */
  faculty_id?: string;
}

export interface RegisterResponse {
  detail: string;
  user: User;
}

export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
  confirm_new_password: string;
}
