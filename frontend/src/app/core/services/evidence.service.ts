import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { firstValueFrom, Observable } from 'rxjs';

import { environment } from '../../../environments/environment';
import { CaptureRole, Evidence, EvidenceVersion, PendingEvidenceCapture, VerificationDecision } from '../models/evidence.model';
import { Paginated } from '../models/pagination.model';

@Injectable({ providedIn: 'root' })
export class EvidenceService {
  private readonly baseUrl = environment.apiBaseUrl;

  constructor(private readonly http: HttpClient) {}

  list(): Observable<Paginated<Evidence>> {
    return this.http.get<Paginated<Evidence>>(`${this.baseUrl}/evidence/`);
  }

  get(id: number): Observable<Evidence> {
    return this.http.get<Evidence>(`${this.baseUrl}/evidence/${id}/`);
  }

  /** Opens (or idempotently re-fetches) the current in-progress evidence
   * version for a participation. This is the sole mechanism by which a
   * resubmission (after Faculty requests one) creates version N+1. */
  open(participationId: number): Observable<Evidence> {
    return this.http.post<Evidence>(`${this.baseUrl}/evidence/`, { participation: participationId });
  }

  addCapture(versionId: number, capture: PendingEvidenceCapture, role: CaptureRole): Observable<unknown> {
    const form = new FormData();
    form.set('capture_role', role);
    form.set('image', capture.blob, `${role.toLowerCase()}.jpg`);
    form.set('device_capture_timestamp', capture.deviceCaptureTimestamp);
    form.set('latitude', String(capture.latitude));
    form.set('longitude', String(capture.longitude));
    form.set('gps_accuracy', String(capture.gpsAccuracy));
    return this.http.post(`${this.baseUrl}/evidence/versions/${versionId}/captures/`, form);
  }

  submit(versionId: number): Observable<EvidenceVersion> {
    return this.http.post<EvidenceVersion>(`${this.baseUrl}/evidence/versions/${versionId}/submit/`, {});
  }

  verify(evidenceId: number, reason = ''): Observable<Evidence> {
    return this.http.post<Evidence>(`${this.baseUrl}/evidence/${evidenceId}/verify/`, { reason });
  }

  reject(evidenceId: number, reason: string): Observable<Evidence> {
    return this.http.post<Evidence>(`${this.baseUrl}/evidence/${evidenceId}/reject/`, { reason });
  }

  requestResubmission(evidenceId: number, reason: string): Observable<Evidence> {
    return this.http.post<Evidence>(`${this.baseUrl}/evidence/${evidenceId}/request-resubmission/`, { reason });
  }

  override(evidenceId: number, decision: VerificationDecision, reason: string): Observable<Evidence> {
    return this.http.post<Evidence>(`${this.baseUrl}/evidence/${evidenceId}/override/`, { decision, reason });
  }

  /**
   * Runs the full open evidence version -> upload capture(s) -> submit
   * version sequence for a completed capture session — the Phase 4
   * successor of ParticipationService.submitCaptureSession, called from
   * both the live-capture component (online) and the offline queue
   * (delayed sync), whether this is a first-time submission or a
   * Faculty-requested resubmission.
   */
  async submitCaptureSession(participationId: number, captures: PendingEvidenceCapture[]): Promise<Evidence> {
    const evidence = await firstValueFrom(this.open(participationId));
    const version = evidence.versions[evidence.versions.length - 1];
    for (const capture of captures) {
      await firstValueFrom(this.addCapture(version.id, capture, capture.role));
    }
    await firstValueFrom(this.submit(version.id));
    return firstValueFrom(this.get(evidence.id));
  }
}
