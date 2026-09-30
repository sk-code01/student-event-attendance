import { Event, RegistrationStatus } from './event.model';

export interface RegistrationStudent {
  id: number;
  username: string;
  email: string;
}

export interface Registration {
  id: number;
  student: RegistrationStudent;
  event: Event;
  status: RegistrationStatus;
  registered_at: string;
  cancelled_at: string | null;
  created_at: string;
}
