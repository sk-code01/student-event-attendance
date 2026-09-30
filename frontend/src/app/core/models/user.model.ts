import { Department } from './department.model';

export type Role = 'STUDENT' | 'FACULTY' | 'EVENT_COORDINATOR' | 'ADMIN';

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: Role;
  university_registration_number: string | null;
  faculty_id: string | null;
  department: Department | null;
  is_active: boolean;
  date_joined: string;
}
