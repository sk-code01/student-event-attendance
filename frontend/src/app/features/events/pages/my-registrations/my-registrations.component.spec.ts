import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { environment } from '../../../../../environments/environment';
import { MyRegistrationsComponent } from './my-registrations.component';
import { Event } from '../../../../core/models/event.model';
import { Registration } from '../../../../core/models/registration.model';

function makeEvent(overrides: Partial<Event> = {}): Event {
  return {
    id: 1, title: 'Tech Fest', description: '', event_date: '2099-12-01', venue: 'Hall', venue_latitude: null, venue_longitude: null,
    category: 'Technical',
    conducting_college: { id: 1, name: 'Engineering College', code: 'ENGG', is_active: true, created_at: '', updated_at: '' },
    created_by: { id: 2, username: 'hodcs' }, status: 'PUBLISHED',
    registration_start_date: '2026-11-01', registration_end_date: '2026-11-20',
    is_registration_open: true, my_registration_status: 'REGISTERED', created_at: '', updated_at: '',
    ...overrides,
  };
}

function makeRegistration(overrides: Partial<Registration> = {}): Registration {
  return {
    id: 10, student: { id: 3, username: 'studentcs', email: 's@example.com' },
    event: makeEvent(), status: 'REGISTERED', registered_at: '2026-01-01T00:00:00Z',
    cancelled_at: null, created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('MyRegistrationsComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MyRegistrationsComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('lists registrations and allows cancelling a future one', () => {
    const fixture = TestBed.createComponent(MyRegistrationsComponent);
    fixture.detectChanges();
    httpMock.expectOne(`${environment.apiBaseUrl}/registrations/`).flush({
      count: 1, next: null, previous: null, results: [makeRegistration()],
    });
    fixture.detectChanges();

    expect(fixture.nativeElement.textContent).toContain('Tech Fest');
    const cancelButton: HTMLButtonElement = fixture.nativeElement.querySelector('button');
    expect(cancelButton).not.toBeNull();

    cancelButton.click();
    httpMock.expectOne(`${environment.apiBaseUrl}/registrations/10/cancel/`).flush(
      makeRegistration({ status: 'CANCELLED', cancelled_at: '2026-01-02T00:00:00Z' }),
    );
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('CANCELLED');
  });

  it('does not offer cancel for an already-cancelled registration', () => {
    const fixture = TestBed.createComponent(MyRegistrationsComponent);
    fixture.detectChanges();
    httpMock.expectOne(`${environment.apiBaseUrl}/registrations/`).flush({
      count: 1, next: null, previous: null, results: [makeRegistration({ status: 'CANCELLED' })],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('button')).toBeNull();
  });

  it('flags the row when the event itself was cancelled', () => {
    const fixture = TestBed.createComponent(MyRegistrationsComponent);
    fixture.detectChanges();
    httpMock.expectOne(`${environment.apiBaseUrl}/registrations/`).flush({
      count: 1, next: null, previous: null,
      results: [makeRegistration({ event: makeEvent({ status: 'CANCELLED' }) })],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Event cancelled');
  });
});
