import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { environment } from '../../../../environments/environment';
import { LoginComponent } from './login.component';
import { User } from '../../../core/models/user.model';

describe('LoginComponent', () => {
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([
          { path: 'student', children: [] },
          { path: 'login', children: [] },
        ]),
      ],
    }).compileComponents();

    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  it('marks the form invalid when fields are empty', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    expect(fixture.componentInstance.form.invalid).toBeTrue();
  });

  it('does not submit while the form is invalid', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.detectChanges();
    fixture.componentInstance.submit();
    expect(fixture.componentInstance.form.touched).toBeTrue();
    httpMock.expectNone(`${environment.apiBaseUrl}/auth/token/`);
  });

  it('shows a friendly error message on invalid credentials', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    fixture.componentInstance.form.setValue({ username: 'alice', password: 'wrong' });
    fixture.componentInstance.submit();

    httpMock
      .expectOne(`${environment.apiBaseUrl}/auth/token/`)
      .flush({ detail: 'No active account found with the given credentials' }, { status: 401, statusText: 'Unauthorized' });

    fixture.detectChanges();
    expect(fixture.componentInstance.errorMessage()).toContain('No active account');
  });

  it('navigates to the role home route on successful login', () => {
    const fixture = TestBed.createComponent(LoginComponent);
    const navigateSpy = spyOn(router, 'navigateByUrl');
    fixture.componentInstance.form.setValue({ username: 'alice', password: 'StrongPass123!' });
    fixture.componentInstance.submit();

    httpMock.expectOne(`${environment.apiBaseUrl}/auth/token/`).flush({ access: 'a', refresh: 'r' });
    const user: User = {
      id: 1,
      username: 'alice',
      full_name: 'Alice',
      university_registration_number: null,
      faculty_id: null,
      email: 'alice@example.com',
      role: 'STUDENT',
      department: null,
      is_active: true,
      date_joined: '2026-01-01T00:00:00Z',
    };
    httpMock.expectOne(`${environment.apiBaseUrl}/users/me/`).flush(user);

    expect(navigateSpy).toHaveBeenCalledWith('/student');
  });
});
