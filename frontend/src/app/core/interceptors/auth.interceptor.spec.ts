import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { environment } from '../../../environments/environment';
import { authInterceptor } from './auth.interceptor';
import { AuthService } from '../services/auth.service';

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let authService: AuthService;

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    authService = TestBed.inject(AuthService);
  });

  afterEach(() => {
    httpMock.verify();
    sessionStorage.clear();
    localStorage.clear();
  });

  it('attaches the Authorization header when an access token is stored', () => {
    sessionStorage.setItem('ssepams_access_token', 'my-access-token');

    http.get('/api/v1/users/me/').subscribe();

    const req = httpMock.expectOne('/api/v1/users/me/');
    expect(req.request.headers.get('Authorization')).toBe('Bearer my-access-token');
    req.flush({});
  });

  it('does not attach a header to the public login endpoint', () => {
    sessionStorage.setItem('ssepams_access_token', 'my-access-token');

    http.post('/api/v1/auth/token/', {}).subscribe();

    const req = httpMock.expectOne('/api/v1/auth/token/');
    expect(req.request.headers.has('Authorization')).toBeFalse();
    req.flush({});
  });

  it('refreshes the access token on a 401 and retries the original request', (done) => {
    sessionStorage.setItem('ssepams_access_token', 'expired-token');
    sessionStorage.setItem('ssepams_refresh_token', 'valid-refresh-token');

    http.get('/api/v1/users/me/').subscribe((body) => {
      expect(body).toEqual({ username: 'alice' });
      expect(authService.accessToken).toBe('new-access-token');
      done();
    });

    const firstAttempt = httpMock.expectOne('/api/v1/users/me/');
    expect(firstAttempt.request.headers.get('Authorization')).toBe('Bearer expired-token');
    firstAttempt.flush({ detail: 'token expired' }, { status: 401, statusText: 'Unauthorized' });

    const refreshReq = httpMock.expectOne(`${environment.apiBaseUrl}/auth/token/refresh/`);
    refreshReq.flush({ access: 'new-access-token' });

    const retry = httpMock.expectOne('/api/v1/users/me/');
    expect(retry.request.headers.get('Authorization')).toBe('Bearer new-access-token');
    retry.flush({ username: 'alice' });
  });
});
