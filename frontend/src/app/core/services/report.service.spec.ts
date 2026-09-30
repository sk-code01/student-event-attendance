import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { ReportService } from './report.service';

describe('ReportService', () => {
  let service: ReportService;
  let httpMock: HttpTestingController;
  const base = `${environment.apiBaseUrl}/reports`;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(ReportService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('lists report types', () => {
    service.types().subscribe();
    const req = httpMock.expectOne(`${base}/`);
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('previews a report with filters', () => {
    service.preview('participation', { date_from: '2026-01-01' }).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${base}/participation/`);
    expect(req.request.params.get('date_from')).toBe('2026-01-01');
    req.flush({ columns: [], rows: [], row_count: 0 });
  });

  it('requests the export as a blob so the auth interceptor can attach the token', () => {
    service.export('participation', 'xlsx').subscribe();
    const req = httpMock.expectOne((r) => r.url === `${base}/participation/export/`);
    expect(req.request.responseType).toBe('blob');
    expect(req.request.params.get('file_format')).toBe('xlsx');
    // `format` is reserved by DRF for content negotiation and must not be sent.
    expect(req.request.params.get('format')).toBeNull();
    req.flush(new Blob(['x']));
  });

  it('passes filters alongside the format', () => {
    service.export('event', 'pdf', { date_from: '2026-01-01', category: 'Technical' }).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${base}/event/export/`);
    expect(req.request.params.get('file_format')).toBe('pdf');
    expect(req.request.params.get('category')).toBe('Technical');
    req.flush(new Blob(['x']));
  });

  describe('filenameFrom', () => {
    it('reads the server-chosen filename', () => {
      const name = service.filenameFrom(
        'attachment; filename="event-20260915-101010.csv"', 'event', 'csv',
      );
      expect(name).toBe('event-20260915-101010.csv');
    });

    it('falls back when the header is missing', () => {
      expect(service.filenameFrom(null, 'event', 'pdf')).toBe('event.pdf');
    });

    it('never lets a header turn into a path', () => {
      const name = service.filenameFrom(
        'attachment; filename="../../etc/passwd"', 'event', 'csv',
      );
      expect(name).toBe('passwd');
      expect(name).not.toContain('/');
      expect(name).not.toContain('..');
    });
  });
});
