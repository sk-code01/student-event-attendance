import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  AnomaliesResponse,
  AnomalyFilters,
  EngagementResponse,
  RecommendationsResponse,
} from '../models/ai.model';

/**
 * AI decision-support API client.
 *
 * Three GETs, nothing else. There is deliberately no method that names another
 * student: the backend derives the subject from the authenticated user, so an
 * IDOR has nothing to target. The service never post-processes a score — the
 * backend owns the model, the thresholds and the wording, and this layer only
 * carries them to the templates.
 */
@Injectable({ providedIn: 'root' })
export class AiService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = environment.apiBaseUrl;

  /** Student only; the API answers 403 for staff accounts. */
  recommendations(limit?: number): Observable<RecommendationsResponse> {
    let params = new HttpParams();
    if (limit !== undefined && limit > 0) {
      params = params.set('limit', String(limit));
    }
    return this.http.get<RecommendationsResponse>(`${this.baseUrl}/recommendations/`, { params });
  }

  /** Risk signals inside the caller's scope. `evidence` narrows to one record
   * the caller may already see; an id outside the scope is a 404. */
  anomalies(filters: AnomalyFilters = {}): Observable<AnomaliesResponse> {
    let params = new HttpParams();
    if (filters.evidence !== undefined && filters.evidence !== null) {
      params = params.set('evidence', String(filters.evidence));
    }
    if (filters.limit !== undefined && filters.limit > 0) {
      params = params.set('limit', String(filters.limit));
    }
    return this.http.get<AnomaliesResponse>(`${this.baseUrl}/anomalies/`, { params });
  }

  engagement(): Observable<EngagementResponse> {
    return this.http.get<EngagementResponse>(`${this.baseUrl}/engagement/`);
  }
}
