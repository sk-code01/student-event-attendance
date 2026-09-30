import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { NotificationService } from './notification.service';

describe('NotificationService', () => {
  let service: NotificationService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    service = TestBed.inject(NotificationService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    service.stopPolling();
    httpMock.verify();
  });

  it('lists notifications with pagination', () => {
    service.list(2).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${environment.apiBaseUrl}/notifications/`);
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('page')).toBe('2');
    expect(req.request.params.get('unread')).toBeNull();
    req.flush({ results: [], count: 0, next: null, previous: null });
  });

  it('adds the unread filter only when asked', () => {
    service.list(1, true).subscribe();
    const req = httpMock.expectOne((r) => r.url === `${environment.apiBaseUrl}/notifications/`);
    expect(req.request.params.get('unread')).toBe('true');
    req.flush({ results: [], count: 0, next: null, previous: null });
  });

  it('marks one read without sending a read_at', () => {
    service.markRead(7).subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/notifications/7/read/`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({});
    req.flush({ id: 7, is_read: true, read_at: '2026-09-15T10:00:00Z' });
  });

  it('decrements the unread signal when one is marked read', () => {
    service.refreshUnreadCount().subscribe();
    httpMock.expectOne(`${environment.apiBaseUrl}/notifications/unread-count/`).flush({ unread: 3 });
    expect(service.unreadCount()).toBe(3);

    service.markRead(7).subscribe();
    httpMock.expectOne(`${environment.apiBaseUrl}/notifications/7/read/`).flush({ id: 7, is_read: true });
    expect(service.unreadCount()).toBe(2);
  });

  it('never drives the unread count below zero', () => {
    service.markRead(7).subscribe();
    httpMock.expectOne(`${environment.apiBaseUrl}/notifications/7/read/`).flush({ id: 7, is_read: true });
    expect(service.unreadCount()).toBe(0);
  });

  it('zeroes the unread signal on mark-all-read', () => {
    service.refreshUnreadCount().subscribe();
    httpMock.expectOne(`${environment.apiBaseUrl}/notifications/unread-count/`).flush({ unread: 5 });

    service.markAllRead().subscribe();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/notifications/read-all/`);
    expect(req.request.method).toBe('POST');
    req.flush({ marked_read: 5 });

    expect(service.unreadCount()).toBe(0);
  });

  it('starts only one polling timer however many times start is called', () => {
    service.startPolling();
    httpMock.expectOne(`${environment.apiBaseUrl}/notifications/unread-count/`).flush({ unread: 1 });

    // A second start must be a no-op rather than leaking a duplicate interval
    // (which would show up here as a second immediate request).
    service.startPolling();
    httpMock.expectNone(`${environment.apiBaseUrl}/notifications/unread-count/`);
  });

  it('clears the badge when polling stops, so a new user sees no stale count', () => {
    service.refreshUnreadCount().subscribe();
    httpMock.expectOne(`${environment.apiBaseUrl}/notifications/unread-count/`).flush({ unread: 4 });
    expect(service.unreadCount()).toBe(4);

    service.stopPolling();
    expect(service.unreadCount()).toBe(0);
  });
});
