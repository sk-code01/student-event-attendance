import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Attendance } from '../models/attendance.model';
import { Paginated } from '../models/pagination.model';

/**
 * Attendance requests and decisions. Reuses the shared auth interceptor for
 * bearer tokens — no authentication logic is duplicated here.
 *
 * There is deliberately no `update()`/`setStatus()`: the backend exposes no
 * writable status field, and state only changes through the approve/reject
 * actions below, which derive the reviewer and review timestamp from the
 * authenticated user server-side.
 */
@Injectable({ providedIn: 'root' })
export class AttendanceService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  /** Role-scoped server-side: students see their own, Faculty/Event Coordinator their
   * department, Admin everything. */
  list(): Observable<Paginated<Attendance>> {
    return this.http.get<Paginated<Attendance>>(`${this.baseUrl}/attendance/`);
  }

  get(id: number): Observable<Attendance> {
    return this.http.get<Attendance>(`${this.baseUrl}/attendance/${id}/`);
  }

  /** Faculty only. The participation must have an effective VERIFIED evidence
   * decision or the backend refuses with a 400. */
  request(participationId: number): Observable<Attendance> {
    return this.http.post<Attendance>(`${this.baseUrl}/attendance/`, { participation: participationId });
  }

  /**
   * Event Coordinator only: records or updates attendance directly.
   *
   * Keyed on the registration rather than the participation, because the case
   * this exists for is the student who never captured and therefore has no
   * participation at all. Faculty are refused by the backend.
   */
  mark(
    registrationId: number,
    status: 'APPROVED' | 'REJECTED',
    reason = '',
  ): Observable<Attendance> {
    return this.http.post<Attendance>(`${this.baseUrl}/attendance/mark/`, {
      registration: registrationId,
      status,
      reason,
    });
  }

  approve(id: number): Observable<Attendance> {
    return this.http.post<Attendance>(`${this.baseUrl}/attendance/${id}/approve/`, {});
  }

  reject(id: number, reason: string): Observable<Attendance> {
    return this.http.post<Attendance>(`${this.baseUrl}/attendance/${id}/reject/`, { reason });
  }
}
