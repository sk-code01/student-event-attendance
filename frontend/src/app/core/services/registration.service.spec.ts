import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { RegistrationService } from './registration.service';

describe('RegistrationService', () => {
  let service: RegistrationService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(RegistrationService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('lists registrations without a filter', () => {
    service.list().subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/registrations/`);
    expect(req.request.method).toBe('GET');
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('lists registrations filtered by event id', () => {
    service.list(7).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${environment.apiBaseUrl}/registrations/` && r.params.get('event') === '7');
    expect(req.request.method).toBe('GET');
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('registers for an event', () => {
    service.register(3).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/registrations/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ event: 3 });
    req.flush({});
  });

  it('cancels a registration', () => {
    service.cancel(9).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/registrations/9/cancel/`);
    expect(req.request.method).toBe('POST');
    req.flush({});
  });
});
