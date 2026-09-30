import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';
import { User } from '../models/user.model';

const MOCK_USER: User = {
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

describe('AuthService', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    sessionStorage.clear();
    localStorage.clear();
  });

  it('starts unauthenticated with no stored token', () => {
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.currentUser()).toBeNull();
  });

  it('login stores tokens and hydrates the current user from /users/me/', (done) => {
    service.login({ username: 'alice', password: 'StrongPass123!' }).subscribe((user) => {
      expect(user.username).toBe('alice');
      expect(service.isAuthenticated()).toBeTrue();
      expect(service.accessToken).toBe('access-token');
      done();
    });

    httpMock.expectOne(`${environment.apiBaseUrl}/auth/token/`).flush({ access: 'access-token', refresh: 'refresh-token' });
    httpMock.expectOne(`${environment.apiBaseUrl}/users/me/`).flush(MOCK_USER);
  });

  it('hasRole reflects the current user role', (done) => {
    service.login({ username: 'alice', password: 'StrongPass123!' }).subscribe(() => {
      expect(service.hasRole('STUDENT')).toBeTrue();
      expect(service.hasRole('ADMIN')).toBeFalse();
      done();
    });

    httpMock.expectOne(`${environment.apiBaseUrl}/auth/token/`).flush({ access: 'access-token', refresh: 'refresh-token' });
    httpMock.expectOne(`${environment.apiBaseUrl}/users/me/`).flush(MOCK_USER);
  });

  it('logout blacklists the refresh token and clears local session state', (done) => {
    service.login({ username: 'alice', password: 'StrongPass123!' }).subscribe(() => {
      service.logout().subscribe(() => {
        expect(service.isAuthenticated()).toBeFalse();
        expect(service.accessToken).toBeNull();
        done();
      });
      httpMock.expectOne(`${environment.apiBaseUrl}/auth/logout/`).flush(null);
    });

    httpMock.expectOne(`${environment.apiBaseUrl}/auth/token/`).flush({ access: 'access-token', refresh: 'refresh-token' });
    httpMock.expectOne(`${environment.apiBaseUrl}/users/me/`).flush(MOCK_USER);
  });

  it('bootstrap resolves to null immediately when no token is stored', (done) => {
    service.bootstrap().subscribe((user) => {
      expect(user).toBeNull();
      done();
    });
  });
});
