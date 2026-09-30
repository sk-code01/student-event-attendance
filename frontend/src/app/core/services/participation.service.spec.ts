import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { ParticipationService } from './participation.service';

describe('ParticipationService', () => {
  let service: ParticipationService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(ParticipationService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('checks eligibility with the event id as a query param', () => {
    service.checkEligibility(5).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${environment.apiBaseUrl}/participations/eligibility/` && r.params.get('event') === '5');
    expect(req.request.method).toBe('GET');
    req.flush({ eligible: true, reason: null, max_gps_accuracy_meters: 50 });
  });

  it('opens a participation for an event', () => {
    service.open(5).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/participations/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ event: 5 });
    req.flush({ id: 1 });
  });

  it('lists the caller\'s participations', () => {
    service.list().subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/participations/`);
    expect(req.request.method).toBe('GET');
    req.flush({ results: [], count: 0, next: null, previous: null });
  });

  it('fetches a single participation', () => {
    service.get(1).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/participations/1/`);
    expect(req.request.method).toBe('GET');
    req.flush({ id: 1 });
  });
});
