import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { EvidenceService } from './evidence.service';
import { PendingEvidenceCapture } from '../models/evidence.model';

const capture: PendingEvidenceCapture = {
  role: 'PRIMARY', blob: new Blob(['x'], { type: 'image/jpeg' }), previewUrl: '',
  deviceCaptureTimestamp: '2026-09-13T12:00:00Z', latitude: 12.9, longitude: 77.5, gpsAccuracy: 10,
};

describe('EvidenceService', () => {
  let service: EvidenceService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(EvidenceService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('opens an evidence version for a participation', () => {
    service.open(42).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/evidence/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ participation: 42 });
    req.flush({ id: 1, versions: [{ id: 10 }] });
  });

  it('uploads a capture as multipart form data to the version endpoint', () => {
    service.addCapture(10, capture, 'PRIMARY').subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/evidence/versions/10/captures/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body instanceof FormData).toBeTrue();
    req.flush({ id: 1 });
  });

  it('submits a version', () => {
    service.submit(10).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/evidence/versions/10/submit/`);
    expect(req.request.method).toBe('POST');
    req.flush({ id: 10, submitted_at: '2026-09-13T12:00:00Z' });
  });

  it('verify/reject/request-resubmission post to their respective decision endpoints', () => {
    service.verify(1, 'looks good').subscribe();
    let req = httpMock.expectOne(`${environment.apiBaseUrl}/evidence/1/verify/`);
    expect(req.request.body).toEqual({ reason: 'looks good' });
    req.flush({ id: 1, status: 'VERIFIED' });

    service.reject(1, 'blurry').subscribe();
    req = httpMock.expectOne(`${environment.apiBaseUrl}/evidence/1/reject/`);
    expect(req.request.body).toEqual({ reason: 'blurry' });
    req.flush({ id: 1, status: 'REJECTED' });

    service.requestResubmission(1, 'retake').subscribe();
    req = httpMock.expectOne(`${environment.apiBaseUrl}/evidence/1/request-resubmission/`);
    expect(req.request.body).toEqual({ reason: 'retake' });
    req.flush({ id: 1, status: 'RESUBMISSION_REQUIRED' });
  });

  it('override posts decision and reason to the override endpoint', () => {
    service.override(1, 'VERIFIED', 'reviewed personally').subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/evidence/1/override/`);
    expect(req.request.body).toEqual({ decision: 'VERIFIED', reason: 'reviewed personally' });
    req.flush({ id: 1, status: 'VERIFIED' });
  });

  it('submitCaptureSession runs open -> upload each capture -> submit -> refetch in order', async () => {
    const resultPromise = service.submitCaptureSession(42, [capture]);

    const openReq = httpMock.expectOne(`${environment.apiBaseUrl}/evidence/`);
    openReq.flush({ id: 7, versions: [{ id: 10 }] });

    await new Promise((resolve) => setTimeout(resolve, 0));

    const captureReq = httpMock.expectOne(`${environment.apiBaseUrl}/evidence/versions/10/captures/`);
    captureReq.flush({ id: 1 });

    await new Promise((resolve) => setTimeout(resolve, 0));

    const submitReq = httpMock.expectOne(`${environment.apiBaseUrl}/evidence/versions/10/submit/`);
    submitReq.flush({ id: 10, submitted_at: '2026-09-13T12:00:00Z' });

    await new Promise((resolve) => setTimeout(resolve, 0));

    const getReq = httpMock.expectOne(`${environment.apiBaseUrl}/evidence/7/`);
    getReq.flush({ id: 7, status: 'SUBMITTED' });

    const result = await resultPromise;
    expect(result.status).toBe('SUBMITTED');
  });
});
