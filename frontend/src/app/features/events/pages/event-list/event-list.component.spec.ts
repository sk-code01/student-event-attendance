import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { environment } from '../../../../../environments/environment';
import { EventListComponent } from './event-list.component';
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

describe('EventListComponent', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EventListComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('shows a loading state then the fetched events', () => {
    const fixture = TestBed.createComponent(EventListComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.loading()).toBeTrue();

    httpMock.expectOne(`${environment.apiBaseUrl}/events/`).flush({
      count: 1, next: null, previous: null, results: [MOCK_EVENT],
    });
    fixture.detectChanges();

    expect(fixture.componentInstance.loading()).toBeFalse();
    expect(fixture.nativeElement.textContent).toContain('Tech Fest');
  });

  it('shows an "already registered" badge when my_registration_status is REGISTERED', () => {
    const fixture = TestBed.createComponent(EventListComponent);
    fixture.detectChanges();
    httpMock.expectOne(`${environment.apiBaseUrl}/events/`).flush({
      count: 1, next: null, previous: null,
      results: [{ ...MOCK_EVENT, my_registration_status: 'REGISTERED' }],
    });
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('You are registered');
  });

  it('shows an error message when the request fails', () => {
    const fixture = TestBed.createComponent(EventListComponent);
    fixture.detectChanges();
    httpMock.expectOne(`${environment.apiBaseUrl}/events/`).error(new ProgressEvent('error'));
    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('Unable to load events');
  });
});
