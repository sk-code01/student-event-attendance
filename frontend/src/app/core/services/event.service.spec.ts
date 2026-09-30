import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { EventService } from './event.service';
import { EventFormValue } from '../models/event.model';

describe('EventService', () => {
  let service: EventService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(EventService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('lists events', () => {
    service.list().subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/events/`);
    expect(req.request.method).toBe('GET');
    req.flush({ count: 0, next: null, previous: null, results: [] });
  });

  it('creates an event with the given payload', () => {
    const payload: EventFormValue = {
      title: 'Tech Fest', description: '', event_date: '2026-12-01', venue: 'Hall',
      category: 'Technical', conducting_college: 1,
      registration_start_date: '2026-11-01', registration_end_date: '2026-11-20',
    };
    service.create(payload).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/events/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(payload);
    req.flush({});
  });

  it('publishes an event', () => {
    service.publish(5).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/events/5/publish/`);
    expect(req.request.method).toBe('POST');
    req.flush({});
  });

  it('cancels an event', () => {
    service.cancel(5).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/events/5/cancel/`);
    expect(req.request.method).toBe('POST');
    req.flush({});
  });

  it('deletes an event', () => {
    service.delete(5).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/events/5/`);
    expect(req.request.method).toBe('DELETE');
    req.flush(null);
  });
});
