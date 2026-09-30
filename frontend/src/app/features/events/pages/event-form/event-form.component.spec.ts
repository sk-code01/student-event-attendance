import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';

import { environment } from '../../../../../environments/environment';
import { EventFormComponent } from './event-form.component';
import { College } from '../../../../core/models/college.model';

const MOCK_COLLEGE: College = {
  id: 1, name: 'Engineering College', code: 'ENGG', is_active: true, created_at: '', updated_at: '',
};

describe('EventFormComponent (create mode)', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EventFormComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({}) } } },
      ],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  function createFixture() {
    const fixture = TestBed.createComponent(EventFormComponent);
    fixture.detectChanges();
    httpMock.expectOne(`${environment.apiBaseUrl}/colleges/?page_size=200`).flush({
      count: 1, next: null, previous: null, results: [MOCK_COLLEGE],
    });
    return fixture;
  }

  afterEach(() => httpMock.verify());

  it('loads in create mode with an empty form', () => {
    const fixture = createFixture();
    expect(fixture.componentInstance.isEditMode()).toBeFalse();
    expect(fixture.componentInstance.form.value.title).toBe('');
  });

  it('flags a title shorter than 3 characters as invalid', () => {
    const fixture = createFixture();
    fixture.componentInstance.form.controls.title.setValue('AB');
    expect(fixture.componentInstance.form.controls.title.invalid).toBeTrue();
  });

  it('flags registration_end_date on or after event_date', () => {
    const fixture = createFixture();
    fixture.componentInstance.form.patchValue({
      registration_start_date: '2026-11-01',
      registration_end_date: '2026-12-01',
      event_date: '2026-12-01',
    });
    expect(fixture.componentInstance.form.hasError('registrationEndNotBeforeEventDate')).toBeTrue();
  });

  it('flags registration_start_date after registration_end_date', () => {
    const fixture = createFixture();
    fixture.componentInstance.form.patchValue({
      registration_start_date: '2026-11-20',
      registration_end_date: '2026-11-01',
    });
    expect(fixture.componentInstance.form.hasError('dateOrder')).toBeTrue();
  });

  it('does not submit an invalid form', () => {
    const fixture = createFixture();
    fixture.componentInstance.submit();
    httpMock.expectNone(`${environment.apiBaseUrl}/events/`);
    expect(fixture.componentInstance.form.touched).toBeTrue();
  });

  it('submits a valid form and creates the event', () => {
    const fixture = createFixture();
    fixture.componentInstance.form.setValue({
      title: 'Annual Tech Fest', description: 'desc', event_date: '2026-12-15',
      venue: 'Main Hall', category: 'Technical', conducting_college: 1,
      registration_start_date: '2026-11-01', registration_end_date: '2026-11-20',
    });
    fixture.componentInstance.submit();
    const req = httpMock.expectOne(`${environment.apiBaseUrl}/events/`);
    expect(req.request.method).toBe('POST');
    req.flush({ id: 1 });
  });

  it('surfaces backend field errors', () => {
    const fixture = createFixture();
    fixture.componentInstance.form.setValue({
      title: 'Annual Tech Fest', description: 'desc', event_date: '2026-12-15',
      venue: 'Main Hall', category: 'Technical', conducting_college: 1,
      registration_start_date: '2026-11-01', registration_end_date: '2026-11-20',
    });
    fixture.componentInstance.submit();
    httpMock.expectOne(`${environment.apiBaseUrl}/events/`).flush(
      { title: ['Title must be at least 3 characters long.'] }, { status: 400, statusText: 'Bad Request' },
    );
    fixture.detectChanges();
    expect(fixture.componentInstance.fieldErrors()['title']).toContain('at least 3');
  });
});

describe('EventFormComponent (edit mode)', () => {
  let httpMock: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [EventFormComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { snapshot: { paramMap: convertToParamMap({ id: '5' }) } } },
      ],
    }).compileComponents();
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('loads the existing event into the form', () => {
    const fixture = TestBed.createComponent(EventFormComponent);
    fixture.detectChanges();
    httpMock.expectOne(`${environment.apiBaseUrl}/colleges/?page_size=200`).flush({
      count: 1, next: null, previous: null, results: [MOCK_COLLEGE],
    });
    httpMock.expectOne(`${environment.apiBaseUrl}/events/5/`).flush({
      id: 5, title: 'Existing Event', description: '', event_date: '2026-12-15', venue: 'Hall',
      category: 'Technical', conducting_college: MOCK_COLLEGE, created_by: { id: 1, username: 'hodcs' },
      status: 'DRAFT', registration_start_date: '2026-11-01', registration_end_date: '2026-11-20',
      is_registration_open: false, my_registration_status: null, created_at: '', updated_at: '',
    });
    fixture.detectChanges();

    expect(fixture.componentInstance.isEditMode()).toBeTrue();
    expect(fixture.componentInstance.form.value.title).toBe('Existing Event');
  });
});
