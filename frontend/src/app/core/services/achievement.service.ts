import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  Achievement,
  AchievementCreatePayload,
  AchievementUpdatePayload,
} from '../models/achievement.model';
import { Paginated } from '../models/pagination.model';

/**
 * Achievement records. `update()` only succeeds on a DRAFT the caller created —
 * the backend refuses anything else, so an approved official record can never
 * be edited from here.
 */
@Injectable({ providedIn: 'root' })
export class AchievementService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  list(): Observable<Paginated<Achievement>> {
    return this.http.get<Paginated<Achievement>>(`${this.baseUrl}/achievements/`);
  }

  get(id: number): Observable<Achievement> {
    return this.http.get<Achievement>(`${this.baseUrl}/achievements/${id}/`);
  }

  /** Faculty create records that go to PENDING_APPROVAL (or DRAFT when
   * `submit_for_approval` is false); Event Coordinator/Admin records are approved on
   * creation. The status is decided server-side from the caller's role — it is
   * never part of this payload. */
  create(payload: AchievementCreatePayload): Observable<Achievement> {
    return this.http.post<Achievement>(`${this.baseUrl}/achievements/`, payload);
  }

  update(id: number, payload: AchievementUpdatePayload): Observable<Achievement> {
    return this.http.patch<Achievement>(`${this.baseUrl}/achievements/${id}/`, payload);
  }

  submit(id: number): Observable<Achievement> {
    return this.http.post<Achievement>(`${this.baseUrl}/achievements/${id}/submit/`, {});
  }

  approve(id: number): Observable<Achievement> {
    return this.http.post<Achievement>(`${this.baseUrl}/achievements/${id}/approve/`, {});
  }

  reject(id: number, reason: string): Observable<Achievement> {
    return this.http.post<Achievement>(`${this.baseUrl}/achievements/${id}/reject/`, { reason });
  }
}
