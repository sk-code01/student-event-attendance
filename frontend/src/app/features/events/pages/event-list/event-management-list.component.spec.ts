import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { environment } from '../../../../../environments/environment';
import { EventManagementListComponent } from './event-management-list.component';
import { AuthService } from '../../../../core/services/auth.service';
import { Event } from '../../../../core/models/event.model';

function makeEvent(overrides: Partial<Event> = {}): Event {
  return {
    id: 1, title: 'Tech Fest', description: '', event_date: '2026-12-01', venue: 'Hall', venue_latitude: null, venue_longitude: null,
    category: 'Technical',
    conducting_college: { id: 1, name: 'Engineering College', code: 'ENGG', is_active: true, created_at: '', updated_at: '' },
    created_by: { id: 2, username: 'hodcs' }, status: 'DRAFT',
    registration_start_date: '2026-11-01', registration_end_date: '2026-11-20',
    is_registration_open: false, my_registration_status: null, created_at: '', updated_at: '',
    ...overrides,
  };
}

describe('EventManagementListComponent', () => {
  let httpMock: HttpTestingController;
  let authService: AuthService;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EventManagementListComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
    authService = TestBed.inject(AuthService);
  });

  afterEach(() => httpMock.verify());

  function loadFixture(events: Event[] = [makeEvent()]) {
    const fixture = TestBed.createComponent(EventManagementListComponent);
    fixture.detectChanges();
    httpMock.expectOne(`${environment.apiBaseUrl}/events/`).flush({
      count: events.length, next: null, previous: null, results: events,
    });
    fixture.detectChanges();
    return fixture;
  }

  it('shows Edit/Publish/Cancel actions for a DRAFT event', () => {
    const fixture = loadFixture();
    const buttons: HTMLButtonElement[] = Array.from(fixture.nativeElement.querySelectorAll('button'));
    expect(buttons.some((b) => b.textContent?.includes('Publish'))).toBeTrue();
    expect(buttons.some((b) => b.textContent?.includes('Cancel'))).toBeTrue();
  });

  it('shows only Cancel for a PUBLISHED event, no Edit', () => {
    const fixture = loadFixture([makeEvent({ status: 'PUBLISHED' })]);
    expect(fixture.nativeElement.textContent).not.toContain('Edit');
    const buttons: HTMLButtonElement[] = Array.from(fixture.nativeElement.querySelectorAll('button'));
    expect(buttons.some((b) => b.textContent?.includes('Publish'))).toBeFalse();
    expect(buttons.some((b) => b.textContent?.includes('Cancel'))).toBeTrue();
  });

  it('shows read-only for a CANCELLED or COMPLETED event', () => {
    const fixture = loadFixture([makeEvent({ status: 'COMPLETED' })]);
    expect(fixture.nativeElement.textContent).toContain('Read-only');
  });

  it('publishes an event and reflects the updated status', () => {
    const fixture = loadFixture();
    fixture.componentInstance.publish(makeEvent());
    httpMock.expectOne(`${environment.apiBaseUrl}/events/1/publish/`).flush(makeEvent({ status: 'PUBLISHED' }));
    fixture.detectChanges();
    expect(fixture.componentInstance.events()[0].status).toBe('PUBLISHED');
  });

  it('shows a link to /event-coordinator/events/new when the user is Event Coordinator', () => {
    spyOn(authService, 'hasRole').and.returnValue(false);
    const fixture = loadFixture();
    const link: HTMLAnchorElement = fixture.nativeElement.querySelector('a.btn-primary');
    expect(link.getAttribute('href')).toContain('/event-coordinator/events/new');
  });

  it('shows a link to /admin/events/new when the user is Admin', () => {
    spyOn(authService, 'hasRole').and.returnValue(true);
    const fixture = loadFixture();
    const link: HTMLAnchorElement = fixture.nativeElement.querySelector('a.btn-primary');
    expect(link.getAttribute('href')).toContain('/admin/events/new');
  });
});
