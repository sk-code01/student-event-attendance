import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { AnalyticsService } from './analytics.service';

describe('AnalyticsService', () => {
  let service: AnalyticsService;
  let httpMock: HttpTestingController;
  const base = `${environment.apiBaseUrl}/analytics`;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(AnalyticsService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('calls each analytics endpoint with GET', () => {
    const calls: [() => void, string][] = [
      [() => service.overview().subscribe(), 'overview'],
      [() => service.participation().subscribe(), 'participation'],
      [() => service.events().subscribe(), 'events'],
      [() => service.registrations().subscribe(), 'registrations'],
      [() => service.attendance().subscribe(), 'attendance'],
      [() => service.od().subscribe(), 'od'],
      [() => service.achievements().subscribe(), 'achievements'],
      [() => service.verification().subscribe(), 'verification'],
      [() => service.trends().subscribe(), 'trends'],
      [() => service.departments().subscribe(), 'departments'],
    ];
    for (const [invoke, path] of calls) {
      invoke();
      const req = httpMock.expectOne((r) => r.url === `${base}/${path}/`);
      expect(req.request.method).toBe('GET');
      req.flush({});
    }
  });

  it('sends only the filters that were actually set', () => {
    service.overview({ date_from: '2026-01-01', category: 'Technical' }).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${base}/overview/`);
    expect(req.request.params.get('date_from')).toBe('2026-01-01');
    expect(req.request.params.get('category')).toBe('Technical');
    expect(req.request.params.get('date_to')).toBeNull();
    expect(req.request.params.get('event')).toBeNull();
    req.flush({});
  });

  it('omits empty and undefined filter values rather than sending blanks', () => {
    service.overview({ date_from: '', category: '   ', event: undefined }).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${base}/overview/`);
    expect(req.request.params.keys().length).toBe(0);
    req.flush({});
  });

  it('passes the trend period through', () => {
    service.trends({ period: 'weekly' }).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${base}/trends/`);
    expect(req.request.params.get('period')).toBe('weekly');
    req.flush({ period: 'weekly', series: [], statistics: {} });
  });

  it('surfaces a 403 from the department endpoint to the caller', () => {
    let status = 0;
    service.departments().subscribe({ error: (e) => (status = e.status) });
    httpMock.expectOne((r) => r.url === `${base}/departments/`)
      .flush({ detail: 'nope' }, { status: 403, statusText: 'Forbidden' });
    expect(status).toBe(403);
  });
});
