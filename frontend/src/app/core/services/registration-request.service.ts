import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Paginated } from '../models/pagination.model';
import { RegistrationRequest } from '../models/registration-request.model';

@Injectable({ providedIn: 'root' })
export class RegistrationRequestService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  list(status?: string): Observable<Paginated<RegistrationRequest>> {
    const url = status
      ? `${this.baseUrl}/users/registration-requests/?status=${encodeURIComponent(status)}`
      : `${this.baseUrl}/users/registration-requests/`;
    return this.http.get<Paginated<RegistrationRequest>>(url);
  }

  approve(id: number): Observable<RegistrationRequest> {
    return this.http.post<RegistrationRequest>(`${this.baseUrl}/users/registration-requests/${id}/approve/`, {});
  }

  reject(id: number, rejectionReason: string): Observable<RegistrationRequest> {
    return this.http.post<RegistrationRequest>(`${this.baseUrl}/users/registration-requests/${id}/reject/`, {
      rejection_reason: rejectionReason,
    });
  }
}
