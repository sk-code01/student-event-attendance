import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { AiService } from './ai.service';

describe('AiService', () => {
  let service: AiService;
  let httpMock: HttpTestingController;
  const base = environment.apiBaseUrl;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(AiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('GETs the three AI endpoints and nothing else', () => {
    service.recommendations().subscribe();
    let req = httpMock.expectOne((r) => r.url === `${base}/recommendations/`);
    expect(req.request.method).toBe('GET');
    expect(req.request.params.keys().length).toBe(0);
    req.flush({});

    service.anomalies().subscribe();
    req = httpMock.expectOne((r) => r.url === `${base}/anomalies/`);
    expect(req.request.method).toBe('GET');
    expect(req.request.params.keys().length).toBe(0);
    req.flush({});

    service.engagement().subscribe();
    req = httpMock.expectOne((r) => r.url === `${base}/engagement/`);
    expect(req.request.method).toBe('GET');
    req.flush({});
  });

  it('passes limit and evidence through as query parameters', () => {
    service.recommendations(3).subscribe();
    let req = httpMock.expectOne((r) => r.url === `${base}/recommendations/`);
    expect(req.request.params.get('limit')).toBe('3');
    req.flush({});

    service.anomalies({ evidence: 42, limit: 5 }).subscribe();
    req = httpMock.expectOne((r) => r.url === `${base}/anomalies/`);
    expect(req.request.params.get('evidence')).toBe('42');
    expect(req.request.params.get('limit')).toBe('5');
    req.flush({});
  });

  it('never sends a student identifier — the subject is always the caller', () => {
    service.recommendations().subscribe();
    const req = httpMock.expectOne((r) => r.url === `${base}/recommendations/`);
    expect(req.request.params.has('student')).toBeFalse();
    expect(req.request.params.has('student_id')).toBeFalse();
    req.flush({});
    expect(Object.keys(service).some((k) => k.toLowerCase().includes('student'))).toBeFalse();
  });

  it('surfaces a 403 on recommendations to the caller', () => {
    let status = 0;
    service.recommendations().subscribe({ error: (e) => (status = e.status) });
    httpMock.expectOne((r) => r.url === `${base}/recommendations/`)
      .flush({ detail: 'personal to students' }, { status: 403, statusText: 'Forbidden' });
    expect(status).toBe(403);
  });

  it('surfaces a 404 for an evidence id outside the scope', () => {
    let status = 0;
    service.anomalies({ evidence: 999 }).subscribe({ error: (e) => (status = e.status) });
    httpMock.expectOne((r) => r.url === `${base}/anomalies/`)
      .flush({ detail: 'Evidence not found.' }, { status: 404, statusText: 'Not Found' });
    expect(status).toBe(404);
  });

  it('delivers an available:false envelope as a normal response, not an error', () => {
    let body: { available: boolean; reason?: string } | undefined;
    service.engagement().subscribe((r) => (body = r));
    httpMock.expectOne((r) => r.url === `${base}/engagement/`).flush({
      available: false, model: 'kmeans', reason: 'INSUFFICIENT_DATA', results: [],
      generated_at: '2026-09-15T00:00:00Z', disclaimer: 'x', inference_ms: 1,
    });
    expect(body?.available).toBeFalse();
    expect(body?.reason).toBe('INSUFFICIENT_DATA');
  });
});
