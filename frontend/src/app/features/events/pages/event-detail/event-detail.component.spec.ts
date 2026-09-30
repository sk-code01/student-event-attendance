import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';

import { environment } from '../../../../../environments/environment';
import { EventDetailComponent } from './event-detail.component';
import { Event } from '../../../../core/models/event.model';

const MOCK_EVENT: Event = {
  id: 1,
  title: 'Tech Fest',
  description: 'A fest.',
  event_date: '2026-12-01',
  venue: 'Main Hall',
  venue_latitude: null,
  venue_longitude: null,
  category: 'Technical',
  conducting_college: { id: 1, name: 'Engineering College', code: 'ENGG', is_active: true, created_at: '', updated_at: '' },
  created_by: { id: 2, username: 'hodcs' },
  status: 'PUBLISHED',
  registration_start_date: '2026-11-01',
  registration_end_date: '2026-11-20',
  is_registration_open: true,
  my_registration_status: null,
  created_at: '',
  updated_at: '',
};

describe('EventDetailComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EventDetailComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id: '1' }) } } },
      ],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  /** Flushes the event fetch and, when the event is REGISTERED, the
   * follow-on participation-eligibility check the component now issues. */
  function flushEventAndEligibility(event: Event, eligible = false, reason: string | null = 'Not eligible.') {
    httpMock.expectOne(`${environment.apiBaseUrl}/events/1/`).flush(event);
    if (event.my_registration_status === 'REGISTERED') {
      httpMock
        .expectOne((r) => r.url === `${environment.apiBaseUrl}/participations/eligibility/`)
        .flush({ eligible, reason, max_gps_accuracy_meters: 50 });
    }
  }

  function loadFixture(event: Event = MOCK_EVENT) {
    const fixture = TestBed.createComponent(EventDetailComponent);
    fixture.detectChanges();
    flushEventAndEligibility(event);
    fixture.detectChanges();
    return fixture;
  }

  it('shows a register button when registration is open and not yet registered', () => {
    const fixture = loadFixture();
    expect(fixture.nativeElement.textContent).toContain('Register');
  });

  it('registers and shows a success message', () => {
    const fixture = loadFixture();
    fixture.componentInstance.register();
    httpMock.expectOne(`${environment.apiBaseUrl}/registrations/`).flush({});
    flushEventAndEligibility({ ...MOCK_EVENT, my_registration_status: 'REGISTERED' });
    fixture.detectChanges();
    expect(fixture.componentInstance.successMessage()).toContain('registered');
  });

  it('shows the backend error message when registration fails', () => {
    const fixture = loadFixture();
    fixture.componentInstance.register();
    httpMock.expectOne(`${environment.apiBaseUrl}/registrations/`).flush(
      { event: ['Registration is not currently open for this event.'] },
      { status: 400, statusText: 'Bad Request' },
    );
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('not currently open');
  });

  it('shows an already-registered badge instead of the register button', () => {
    const fixture = loadFixture({ ...MOCK_EVENT, my_registration_status: 'REGISTERED' });
    expect(fixture.nativeElement.textContent).toContain("You're registered");
    expect(fixture.nativeElement.querySelector('button')).toBeNull();
  });

  it('shows a link to mark participation when eligible', () => {
    const fixture = TestBed.createComponent(EventDetailComponent);
    fixture.detectChanges();
    flushEventAndEligibility({ ...MOCK_EVENT, my_registration_status: 'REGISTERED' }, true, null);
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Mark participation');
  });

  it('shows the ineligibility reason instead of a participation link when not eligible', () => {
    const fixture = TestBed.createComponent(EventDetailComponent);
    fixture.detectChanges();
    flushEventAndEligibility(
      { ...MOCK_EVENT, my_registration_status: 'REGISTERED' }, false, 'Participation is only available on the event date.',
    );
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('only available on the event date');
    expect(fixture.nativeElement.textContent).not.toContain('Mark Participation');
  });
});
