import { Department } from './department.model';
import { Role, User } from './user.model';

export type RegistrationStatus = 'PENDING' | 'APPROVED' | 'REJECTED';

export interface RegistrationRequest {
  id: number;
  user: User;
  role: Role;
  department: Department;
  status: RegistrationStatus;
  requested_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  rejection_reason: string;
}

export interface RegistrationStatusResult {
  status: RegistrationStatus;
  requested_at: string;
  rejection_reason?: string;
}
