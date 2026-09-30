import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { Certificate, CertificateEligibility } from '../models/certificate.model';
import { Paginated } from '../models/pagination.model';

/**
 * Certificates: student upload, Faculty verification, and the Event
 * Coordinator's decisions.
 *
 * There is no `update()`: a certificate's state only ever changes through the
 * decision actions below, each of which derives the reviewer and the timestamp
 * from the authenticated user server-side. The file itself is never
 * re-uploaded onto an existing record — a new attempt is a new record, which
 * is what keeps the trail of what was submitted when.
 */
@Injectable({ providedIn: 'root' })
export class CertificateService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  /** Role-scoped server-side: a student sees their own, Faculty and the Event
   *  Coordinator their department's, Admin everything. */
  list(): Observable<Paginated<Certificate>> {
    return this.http.get<Paginated<Certificate>>(`${this.baseUrl}/certificates/`);
  }

  get(id: number): Observable<Certificate> {
    return this.http.get<Certificate>(`${this.baseUrl}/certificates/${id}/`);
  }

  /** Whether this participation can accept a certificate right now. */
  eligibility(participationId: number): Observable<CertificateEligibility> {
    return this.http.get<CertificateEligibility>(
      `${this.baseUrl}/certificates/eligibility/`,
      { params: { participation: participationId } },
    );
  }

  /** Student only. The attempt number, hash and owner are all server-derived. */
  upload(participationId: number, file: File): Observable<Certificate> {
    const body = new FormData();
    body.append('participation', String(participationId));
    body.append('file', file);
    return this.http.post<Certificate>(`${this.baseUrl}/certificates/upload/`, body);
  }

  /** Faculty only. A rejection must carry a reason; the backend refuses
   *  otherwise, and so does the database. */
  decide(id: number, decision: 'VERIFIED' | 'REJECTED', reason = ''): Observable<Certificate> {
    return this.http.post<Certificate>(
      `${this.baseUrl}/certificates/${id}/decision/`, { decision, reason },
    );
  }

  /** Event Coordinator's final decision, available only once Faculty have
   *  verified the certificate. */
  finalDecision(id: number, decision: 'ACCEPTED' | 'REJECTED', reason = ''): Observable<Certificate> {
    return this.http.post<Certificate>(
      `${this.baseUrl}/certificates/${id}/final-decision/`, { decision, reason },
    );
  }

  /** Event Coordinator only, and only once the student's three attempts are
   *  used up — the release valve for a student who can no longer resubmit. */
  acceptExhausted(id: number): Observable<Certificate> {
    return this.http.post<Certificate>(`${this.baseUrl}/certificates/${id}/accept/`, {});
  }
}
