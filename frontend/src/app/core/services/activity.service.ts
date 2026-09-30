import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { ActivityRecord } from '../models/activity.model';
import { Paginated } from '../models/pagination.model';

export interface AuditFilters {
  action?: string;
  actor?: number;
  date_from?: string;
  date_to?: string;
  search?: string;
  page?: number;
}

/**
 * Two scopes over the same existing AuditLog:
 *
 * - `myActivity()` -> `/activity/`, always the caller's own records only.
 * - `auditTrail()` -> `/audit/`, the administrative trail. Admin sees
 *   everything; Event Coordinator sees their own department; Student/Faculty get 403.
 *
 * No second audit store was created in Phase 6.
 */
@Injectable({ providedIn: 'root' })
export class ActivityService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  myActivity(page = 1): Observable<Paginated<ActivityRecord>> {
    return this.http.get<Paginated<ActivityRecord>>(`${this.baseUrl}/activity/`, {
      params: { page: String(page) },
    });
  }

  auditTrail(filters: AuditFilters = {}): Observable<Paginated<ActivityRecord>> {
    const params: Record<string, string> = {};
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && String(value).trim() !== '') {
        params[key] = String(value);
      }
    }
    return this.http.get<Paginated<ActivityRecord>>(`${this.baseUrl}/audit/`, { params });
  }
}
