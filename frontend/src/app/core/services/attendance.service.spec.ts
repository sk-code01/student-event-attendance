import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { AttendanceService } from './attendance.service';

describe('AttendanceService', () => {
  let service: AttendanceService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(AttendanceService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('lists attendance records', () => {
    service.list().subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/attendance/`);
    expect(req.request.method).toBe('GET');
    req.flush({ results: [], count: 0, next: null, previous: null });
  });

  it('requests attendance with only the participation id', () => {
    service.request(42).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/attendance/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ participation: 42 });
    req.flush({ id: 1, status: 'PENDING' });
  });

  it('approves without sending any reviewer or timestamp', () => {
    service.approve(7).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/attendance/7/approve/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush({ id: 7, status: 'APPROVED' });
  });

  it('rejects with a reason', () => {
    service.reject(7, 'not eligible').subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/attendance/7/reject/`);
    expect(req.request.body).toEqual({ reason: 'not eligible' });
    req.flush({ id: 7, status: 'REJECTED' });
  });

  it('fetches a single record', () => {
    service.get(3).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/attendance/3/`);
    expect(req.request.method).toBe('GET');
    req.flush({ id: 3 });
  });
});
