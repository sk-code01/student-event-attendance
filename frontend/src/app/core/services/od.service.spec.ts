import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { OdService } from './od.service';

describe('OdService', () => {
  let service: OdService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(OdService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('targets the separate /od/ resource, never /attendance/', () => {
    service.list().subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/od/`);
    expect(req.request.url).not.toContain('attendance');
    req.flush({ results: [], count: 0, next: null, previous: null });
  });

  it('requests OD with a participation id and a reason', () => {
    service.request(42, 'Representing the college').subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/od/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ participation: 42, reason: 'Representing the college' });
    req.flush({ id: 1, status: 'PENDING' });
  });

  it('approves and rejects through the dedicated actions', () => {
    service.approve(5).subscribe();
    let req = httpMock.expectOne(`${environment.apiBaseUrl}/od/5/approve/`);
    expect(req.request.body).toEqual({});
    req.flush({ id: 5, status: 'APPROVED' });

    service.reject(5, 'not applicable').subscribe();
    req = httpMock.expectOne(`${environment.apiBaseUrl}/od/5/reject/`);
    expect(req.request.body).toEqual({ reason: 'not applicable' });
    req.flush({ id: 5, status: 'REJECTED' });
  });
});
