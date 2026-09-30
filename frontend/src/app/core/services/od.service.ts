import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { ODRequest } from '../models/od.model';
import { Paginated } from '../models/pagination.model';

/**
 * OD requests and decisions — a separate resource from AttendanceService,
 * matching the backend's separate `/api/v1/od/` app. Nothing here reads or
 * writes attendance.
 */
@Injectable({ providedIn: 'root' })
export class OdService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  list(): Observable<Paginated<ODRequest>> {
    return this.http.get<Paginated<ODRequest>>(`${this.baseUrl}/od/`);
  }

  get(id: number): Observable<ODRequest> {
    return this.http.get<ODRequest>(`${this.baseUrl}/od/${id}/`);
  }

  /** Faculty only; `reason` is the justification the Event Coordinator reviews and is
   * required by the backend. */
  request(participationId: number, reason: string): Observable<ODRequest> {
    return this.http.post<ODRequest>(`${this.baseUrl}/od/`, { participation: participationId, reason });
  }

  approve(id: number): Observable<ODRequest> {
    return this.http.post<ODRequest>(`${this.baseUrl}/od/${id}/approve/`, {});
  }

  reject(id: number, reason: string): Observable<ODRequest> {
    return this.http.post<ODRequest>(`${this.baseUrl}/od/${id}/reject/`, { reason });
  }
}
