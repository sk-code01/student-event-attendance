import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { environment } from '../../../../environments/environment';
import { RegisterComponent } from './register.component';
import { Department } from '../../../core/models/department.model';

const DEPARTMENTS: Department[] = [
  { id: 1, name: 'Computer Science', code: 'CS', is_active: true, created_at: '2026-01-01T00:00:00Z' },
];

describe('RegisterComponent', () => {
  let httpMock: HttpTestingController;

  function createAndLoadDepartments() {
    const fixture = TestBed.createComponent(RegisterComponent);
    fixture.detectChanges();
    // The form asks for EVERY department, not the default first page:
    // a registration dropdown that silently stops at 20 would hide the
    // applicant's own department from them.
    httpMock.expectOne(`${environment.apiBaseUrl}/departments/?page_size=200`).flush({
      count: 1, next: null, previous: null, results: DEPARTMENTS,
    });
    return fixture;
  }

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RegisterComponent],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('loads departments on init', () => {
    const fixture = createAndLoadDepartments();
    expect(fixture.componentInstance.departments()).toEqual(DEPARTMENTS);
  });

  it('flags mismatched passwords as invalid', () => {
    const fixture = createAndLoadDepartments();
    const form = fixture.componentInstance.form;
    form.setValue({
      username: 'newstudent',
      email: 'new@example.com',
      full_name: 'New Student',
      password: 'StrongPass123!',
      confirm_password: 'Different123!',
      role: 'STUDENT',
      department: 1,
      university_registration_number: '1AY22MC045',
      faculty_id: '',
    });
    expect(form.hasError('passwordMismatch')).toBeTrue();
  });

  it('rejects usernames with uppercase letters or symbols', () => {
    const fixture = createAndLoadDepartments();
    const usernameControl = fixture.componentInstance.form.controls.username;
    usernameControl.setValue('Bad-User');
    expect(usernameControl.hasError('pattern')).toBeTrue();
  });

  it('shows a pending-approval message after successful submission', () => {
    const fixture = createAndLoadDepartments();
    fixture.componentInstance.form.setValue({
      username: 'newstudent',
      email: 'new@example.com',
      full_name: 'New Student',
      password: 'StrongPass123!',
      confirm_password: 'StrongPass123!',
      role: 'STUDENT',
      department: 1,
      university_registration_number: '1AY22MC045',
      faculty_id: '',
    });

    fixture.componentInstance.submit();
    httpMock.expectOne(`${environment.apiBaseUrl}/auth/register/`).flush({
      detail: 'Registration submitted.',
      user: {},
    });

    fixture.detectChanges();
    expect(fixture.componentInstance.submitted()).toBeTrue();
    expect(fixture.nativeElement.textContent).toContain('pending Event Coordinator approval');
  });

  // ---------------------------------------------------------------------
  // Role-specific identity field
  //
  // A Student is issued a university registration number; Faculty and Event
  // Coordinator are both issued the college's Faculty ID, because an Event
  // Coordinator *is* a faculty member.
  // ---------------------------------------------------------------------

  function identityFieldIds(fixture: ReturnType<typeof TestBed.createComponent>): string[] {
    const element = fixture.nativeElement as HTMLElement;
    return ['university_registration_number', 'faculty_id']
      .filter((id) => element.querySelector(`#${id}`) !== null);
  }

  function fillCommonFields(fixture: ReturnType<typeof TestBed.createComponent>): void {
    (fixture.componentInstance as RegisterComponent).form.patchValue({
      username: 'someone',
      email: 'someone@example.com',
      full_name: 'Some One',
      password: 'StrongPass123!',
      confirm_password: 'StrongPass123!',
      department: 1,
    });
  }

  it('shows the university registration number for a Student, and nothing else', () => {
    const fixture = createAndLoadDepartments();
    fixture.componentInstance.form.controls.role.setValue('STUDENT');
    fixture.detectChanges();

    expect(identityFieldIds(fixture)).toEqual(['university_registration_number']);
  });

  it('shows the Faculty ID for Faculty, and nothing else', () => {
    const fixture = createAndLoadDepartments();
    fixture.componentInstance.form.controls.role.setValue('FACULTY');
    fixture.detectChanges();

    expect(identityFieldIds(fixture)).toEqual(['faculty_id']);
  });

  it('shows the Faculty ID for an Event Coordinator, and nothing else', () => {
    const fixture = createAndLoadDepartments();
    fixture.componentInstance.form.controls.role.setValue('EVENT_COORDINATOR');
    fixture.detectChanges();

    expect(identityFieldIds(fixture)).toEqual(['faculty_id']);
  });

  it('requires the identifier the selected role is issued', () => {
    const fixture = createAndLoadDepartments();
    const form = fixture.componentInstance.form;

    form.controls.role.setValue('STUDENT');
    expect(form.controls.university_registration_number.hasError('required')).toBeTrue();
    expect(form.controls.faculty_id.hasError('required')).toBeFalse();

    for (const role of ['FACULTY', 'EVENT_COORDINATOR']) {
      form.controls.role.setValue(role);
      expect(form.controls.faculty_id.hasError('required'))
        .withContext(`${role} must require a Faculty ID`)
        .toBeTrue();
      expect(form.controls.university_registration_number.hasError('required'))
        .withContext(`${role} must not require a registration number`)
        .toBeFalse();
    }
  });

  it('clears the registration number when switching from Student to Faculty', () => {
    const fixture = createAndLoadDepartments();
    const form = fixture.componentInstance.form;

    form.controls.role.setValue('STUDENT');
    form.controls.university_registration_number.setValue('1AY22MC001');
    form.controls.role.setValue('FACULTY');

    expect(form.controls.university_registration_number.value).toBe('');
  });

  it('keeps the Faculty ID when switching between the two faculty roles', () => {
    // Both roles carry the same identifier, so clearing it would make the
    // applicant retype what they already entered.
    const fixture = createAndLoadDepartments();
    const form = fixture.componentInstance.form;

    form.controls.role.setValue('FACULTY');
    form.controls.faculty_id.setValue('FAC-1024');
    form.controls.role.setValue('EVENT_COORDINATOR');

    expect(form.controls.faculty_id.value).toBe('FAC-1024');
  });

  it('never submits the identifier belonging to the other role', () => {
    const fixture = createAndLoadDepartments();
    const form = fixture.componentInstance.form;

    fillCommonFields(fixture);
    form.controls.role.setValue('STUDENT');
    form.controls.university_registration_number.setValue('1AY22MC001');
    // Switching role is what must drop it — not the template hiding the input.
    form.controls.role.setValue('EVENT_COORDINATOR');
    form.controls.faculty_id.setValue('FAC-1024');

    fixture.componentInstance.submit();

    const request = httpMock.expectOne(`${environment.apiBaseUrl}/auth/register/`);
    expect(request.request.body.faculty_id).toBe('FAC-1024');
    expect(request.request.body.university_registration_number).toBeUndefined();
    request.flush({ detail: 'Registered.' });
  });

  it('sends only the registration number for a Student', () => {
    const fixture = createAndLoadDepartments();
    const form = fixture.componentInstance.form;

    fillCommonFields(fixture);
    form.controls.role.setValue('STUDENT');
    form.controls.university_registration_number.setValue('1AY22MC001');

    fixture.componentInstance.submit();

    const request = httpMock.expectOne(`${environment.apiBaseUrl}/auth/register/`);
    expect(request.request.body.university_registration_number).toBe('1AY22MC001');
    expect(request.request.body.faculty_id).toBeUndefined();
    request.flush({ detail: 'Registered.' });
  });

  it('displays a Faculty ID error returned by the API', () => {
    const fixture = createAndLoadDepartments();
    const form = fixture.componentInstance.form;

    fillCommonFields(fixture);
    form.controls.role.setValue('EVENT_COORDINATOR');
    form.controls.faculty_id.setValue('FAC-1024');

    fixture.componentInstance.submit();

    httpMock.expectOne(`${environment.apiBaseUrl}/auth/register/`).flush(
      { faculty_id: ['This Faculty ID is already registered.'] },
      { status: 400, statusText: 'Bad Request' },
    );
    fixture.detectChanges();

    expect(fixture.componentInstance.fieldErrors()['faculty_id'])
      .toBe('This Faculty ID is already registered.');
  });

  it('surfaces backend field errors, e.g. duplicate username', () => {
    const fixture = createAndLoadDepartments();
    fixture.componentInstance.form.setValue({
      username: 'taken',
      email: 'new@example.com',
      full_name: 'New Student',
      password: 'StrongPass123!',
      confirm_password: 'StrongPass123!',
      role: 'STUDENT',
      department: 1,
      university_registration_number: '1AY22MC045',
      faculty_id: '',
    });

    fixture.componentInstance.submit();
    httpMock
      .expectOne(`${environment.apiBaseUrl}/auth/register/`)
      .flush({ username: ['This username is already taken.'] }, { status: 400, statusText: 'Bad Request' });

    fixture.detectChanges();
    expect(fixture.componentInstance.fieldErrors()['username']).toContain('already taken');
  });
});
