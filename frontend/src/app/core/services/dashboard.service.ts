import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Dashboard } from '../models/dashboard.model';

/**
 * One role-aware dashboard endpoint. There is no per-role URL to request, so
 * a Student cannot ask for the Admin payload — the backend derives scope from
 * the authenticated user and never computes out-of-scope data at all.
 */
@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  get(): Observable<Dashboard> {
    return this.http.get<Dashboard>(`${this.baseUrl}/dashboard/`);
  }
}
