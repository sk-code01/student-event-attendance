import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  AchievementAnalytics,
  AnalyticsFilters,
  AnalyticsOverview,
  ApprovalAnalytics,
  DepartmentAnalytics,
  EventAnalytics,
  ParticipationAnalytics,
  RegistrationAnalytics,
  Trends,
  VerificationAnalytics,
} from '../models/analytics.model';

/**
 * Analytics API client.
 *
 * Every method is a plain GET returning pre-aggregated values. This service
 * deliberately contains **no arithmetic** — the backend decides what a role
 * may see, how each value is calculated and which filters are valid, so
 * recomputing anything here would create a second, unauthoritative answer.
 *
 * Filters are passed through as query parameters. They can only narrow what
 * the caller is already entitled to; the server refuses a foreign id with
 * 403/404 rather than honouring it.
 */
@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private readonly baseUrl = `${environment.apiBaseUrl}/analytics`;

  constructor(private readonly http: HttpClient) {}

  private params(filters: AnalyticsFilters = {}): HttpParams {
    let params = new HttpParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value !== undefined && value !== null && String(value).trim() !== '') {
        params = params.set(key, String(value));
      }
    }
    return params;
  }

  overview(filters: AnalyticsFilters = {}): Observable<AnalyticsOverview> {
    return this.http.get<AnalyticsOverview>(`${this.baseUrl}/overview/`, { params: this.params(filters) });
  }

  participation(filters: AnalyticsFilters = {}): Observable<ParticipationAnalytics> {
    return this.http.get<ParticipationAnalytics>(
      `${this.baseUrl}/participation/`, { params: this.params(filters) },
    );
  }

  events(filters: AnalyticsFilters = {}): Observable<EventAnalytics> {
    return this.http.get<EventAnalytics>(`${this.baseUrl}/events/`, { params: this.params(filters) });
  }

  registrations(filters: AnalyticsFilters = {}): Observable<RegistrationAnalytics> {
    return this.http.get<RegistrationAnalytics>(
      `${this.baseUrl}/registrations/`, { params: this.params(filters) },
    );
  }

  attendance(filters: AnalyticsFilters = {}): Observable<ApprovalAnalytics> {
    return this.http.get<ApprovalAnalytics>(`${this.baseUrl}/attendance/`, { params: this.params(filters) });
  }

  od(filters: AnalyticsFilters = {}): Observable<ApprovalAnalytics> {
    return this.http.get<ApprovalAnalytics>(`${this.baseUrl}/od/`, { params: this.params(filters) });
  }

  achievements(filters: AnalyticsFilters = {}): Observable<AchievementAnalytics> {
    return this.http.get<AchievementAnalytics>(
      `${this.baseUrl}/achievements/`, { params: this.params(filters) },
    );
  }

  verification(filters: AnalyticsFilters = {}): Observable<VerificationAnalytics> {
    return this.http.get<VerificationAnalytics>(
      `${this.baseUrl}/verification/`, { params: this.params(filters) },
    );
  }

  trends(filters: AnalyticsFilters = {}): Observable<Trends> {
    return this.http.get<Trends>(`${this.baseUrl}/trends/`, { params: this.params(filters) });
  }

  /** Event Coordinator (own department) and Admin (all) only; other roles get 403. */
  departments(filters: AnalyticsFilters = {}): Observable<DepartmentAnalytics> {
    return this.http.get<DepartmentAnalytics>(
      `${this.baseUrl}/departments/`, { params: this.params(filters) },
    );
  }
}
