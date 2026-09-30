import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import {
  AdminPasswordReset,
  AdminPasswordResetResult,
  AdminUser,
  AdminUserDetail,
  AdminUserFilters,
  AdminUserStats,
  AdminUserUpdate,
} from '../models/admin-user.model';
import { Paginated } from '../models/pagination.model';
import { User } from '../models/user.model';

export interface ProvisionEventCoordinatorRequest {
  username: string;
  email: string;
  password: string;
  confirm_password: string;
  department: number;
}

/**
 * Admin user management.
 *
 * Every method here is Admin-only, and that is enforced by the API, not by
 * this class — the service exists to shape requests, never to decide who may
 * make them. A non-Admin calling any of these receives a 403 from the
 * backend.
 *
 * `resetPassword` sends a plaintext password over the wire exactly once, to
 * an endpoint that hashes it with `set_password()` and returns nothing about
 * it. The password is never stored in a signal, never written to
 * `localStorage`, and never logged.
 */
@Injectable({ providedIn: 'root' })
export class UserAdminService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  provisionEventCoordinator(payload: ProvisionEventCoordinatorRequest): Observable<User> {
    return this.http.post<User>(`${this.baseUrl}/users/provision-event-coordinator/`, payload);
  }

  list(filters: AdminUserFilters = {}): Observable<Paginated<AdminUser>> {
    let params = new HttpParams();
    // Only non-empty values are sent: an empty `search=` would be a
    // meaningless filter, and `status=all` is the API default.
    if (filters.search?.trim()) {
      params = params.set('search', filters.search.trim());
    }
    if (filters.role) {
      params = params.set('role', filters.role);
    }
    if (filters.department) {
      params = params.set('department', filters.department);
    }
    if (filters.status && filters.status !== 'all') {
      params = params.set('status', filters.status);
    }
    if (filters.page && filters.page > 1) {
      params = params.set('page', String(filters.page));
    }
    return this.http.get<Paginated<AdminUser>>(`${this.baseUrl}/users/`, { params });
  }

  stats(): Observable<AdminUserStats> {
    return this.http.get<AdminUserStats>(`${this.baseUrl}/users/stats/`);
  }

  get(id: number): Observable<AdminUserDetail> {
    return this.http.get<AdminUserDetail>(`${this.baseUrl}/users/${id}/`);
  }

  update(id: number, payload: AdminUserUpdate): Observable<AdminUserDetail> {
    return this.http.patch<AdminUserDetail>(`${this.baseUrl}/users/${id}/`, payload);
  }

  activate(id: number): Observable<AdminUserDetail> {
    return this.http.post<AdminUserDetail>(`${this.baseUrl}/users/${id}/activate/`, {});
  }

  deactivate(id: number): Observable<AdminUserDetail> {
    return this.http.post<AdminUserDetail>(`${this.baseUrl}/users/${id}/deactivate/`, {});
  }

  resetPassword(id: number, payload: AdminPasswordReset): Observable<AdminPasswordResetResult> {
    return this.http.post<AdminPasswordResetResult>(`${this.baseUrl}/users/${id}/reset-password/`, payload);
  }
}
