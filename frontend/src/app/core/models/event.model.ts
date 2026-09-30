import { College } from './college.model';

export type EventStatus = 'DRAFT' | 'PUBLISHED' | 'CANCELLED' | 'COMPLETED';
export type RegistrationStatus = 'REGISTERED' | 'CANCELLED';

export interface EventSummary {
  id: number;
  username: string;
}

export interface Event {
  id: number;
  title: string;
  description: string;
  event_date: string;
  venue: string;
  venue_latitude: string | null;
  venue_longitude: string | null;
  category: string;
  conducting_college: College;
  created_by: EventSummary;
  status: EventStatus;
  registration_start_date: string;
  registration_end_date: string;
  is_registration_open: boolean;
  my_registration_status: RegistrationStatus | null;
  created_at: string;
  updated_at: string;
}

export interface EventFormValue {
  title: string;
  description: string;
  event_date: string;
  venue: string;
  category: string;
  conducting_college: number;
  registration_start_date: string;
  registration_end_date: string;
}
