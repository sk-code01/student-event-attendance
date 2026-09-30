import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Event, EventFormValue } from '../models/event.model';
import { Paginated } from '../models/pagination.model';

@Injectable({ providedIn: 'root' })
export class EventService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  list(): Observable<Paginated<Event>> {
    return this.http.get<Paginated<Event>>(`${this.baseUrl}/events/`);
  }

  get(id: number): Observable<Event> {
    return this.http.get<Event>(`${this.baseUrl}/events/${id}/`);
  }

  create(payload: EventFormValue): Observable<Event> {
    return this.http.post<Event>(`${this.baseUrl}/events/`, payload);
  }

  update(id: number, payload: EventFormValue): Observable<Event> {
    return this.http.patch<Event>(`${this.baseUrl}/events/${id}/`, payload);
  }

  publish(id: number): Observable<Event> {
    return this.http.post<Event>(`${this.baseUrl}/events/${id}/publish/`, {});
  }

  cancel(id: number): Observable<Event> {
    return this.http.post<Event>(`${this.baseUrl}/events/${id}/cancel/`, {});
  }

  delete(id: number): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/events/${id}/`);
  }
}
