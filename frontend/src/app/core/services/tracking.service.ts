import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Paginated } from '../models/pagination.model';
import { TrackingFilters, TrackingRow } from '../models/tracking.model';

/**
 * The department-wide tracking view.
 *
 * Read-only by design: this endpoint answers "where does every registered
 * student stand?" and never changes anything. Acting on a row — recording
 * attendance, deciding a certificate — goes through the service that owns
 * that record.
 */
@Injectable({ providedIn: 'root' })
export class TrackingService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  /**
   * Scoped server-side to the caller's department; a student gets only their
   * own rows, which is also what makes this their chronological history.
   * Empty filters are dropped rather than sent as blanks, so the request says
   * exactly what was asked for.
   */
  list(filters: TrackingFilters = {}): Observable<Paginated<TrackingRow>> {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== null && value !== undefined && String(value).trim() !== '') {
        params = params.set(key, String(value));
      }
    }
    return this.http.get<Paginated<TrackingRow>>(`${this.baseUrl}/registrations/tracking/`, { params });
  }

  /** One student's complete history, oldest event first. */
  forStudent(studentId: number): Observable<Paginated<TrackingRow>> {
    return this.list({ student: studentId });
  }
}
