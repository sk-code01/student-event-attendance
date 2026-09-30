import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Paginated } from '../models/pagination.model';
import { EligibilityResult, Participation } from '../models/participation.model';

@Injectable({ providedIn: 'root' })
export class ParticipationService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  list(): Observable<Paginated<Participation>> {
    return this.http.get<Paginated<Participation>>(`${this.baseUrl}/participations/`);
  }

  get(id: number): Observable<Participation> {
    return this.http.get<Participation>(`${this.baseUrl}/participations/${id}/`);
  }

  checkEligibility(eventId: number): Observable<EligibilityResult> {
    return this.http.get<EligibilityResult>(`${this.baseUrl}/participations/eligibility/`, {
      params: { event: eventId },
    });
  }

  /** Opens (or idempotently re-fetches) a DRAFT Participation for the
   * caller's own registration. Capture upload/submission has lived under
   * EvidenceService since Phase 4 — see its submitCaptureSession(). */
  open(eventId: number): Observable<Participation> {
    return this.http.post<Participation>(`${this.baseUrl}/participations/`, { event: eventId });
  }
}
