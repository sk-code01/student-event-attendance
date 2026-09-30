import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Paginated } from '../models/pagination.model';
import { Registration } from '../models/registration.model';

@Injectable({ providedIn: 'root' })
export class RegistrationService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  list(eventId?: number): Observable<Paginated<Registration>> {
    const params = eventId ? new HttpParams().set('event', eventId) : undefined;
    return this.http.get<Paginated<Registration>>(`${this.baseUrl}/registrations/`, { params });
  }

  register(eventId: number): Observable<Registration> {
    return this.http.post<Registration>(`${this.baseUrl}/registrations/`, { event: eventId });
  }

  cancel(registrationId: number): Observable<Registration> {
    return this.http.post<Registration>(`${this.baseUrl}/registrations/${registrationId}/cancel/`, {});
  }
}
