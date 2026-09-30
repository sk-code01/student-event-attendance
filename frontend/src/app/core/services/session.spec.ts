import { HttpErrorResponse, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed, fakeAsync, tick } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { environment } from '../../../environments/environment';
import { authInterceptor } from '../interceptors/auth.interceptor';
import { AuthService } from './auth.service';
import { SessionService } from './session.service';
import { User } from '../models/user.model';

/**
 * Session lifecycle: inactivity timeout, token persistence, expiry handling
 * and cross-tab behaviour (requirement 36).
 *
 * The tab-close requirement is asserted through the *persistence mechanism*
 * rather than by firing an unload event. A unit test cannot close a browser
 * tab, and an unload handler proves nothing anyway: what makes the session end
 * with the tab is that the tokens live in sessionStorage, which the browser
 * itself discards. So that is what these tests check.
 */

const ACCESS_KEY = 'ssepams_access_token';
const REFRESH_KEY = 'ssepams_refresh_token';
const LAST_ACTIVITY_KEY = 'ssepams_last_activity_at';

const USER: User = {
  id: 1, username: 'stu1', email: 'stu1@example.com', full_name: 'Stu One',
  university_registration_number: '1AY22MC001', faculty_id: null,
  role: 'STUDENT', department: null, is_active: true, date_joined: '',
} as User;

describe('Session lifecycle', () => {
  let auth: AuthService;
  let session: SessionService;
  let http: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();

    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });

    auth = TestBed.inject(AuthService);
    session = TestBed.inject(SessionService);
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    spyOn(router, 'navigate').and.resolveTo(true);
  });

  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  function signIn(): void {
    auth.login({ username: 'stu1', password: 'pw' }).subscribe();
    http.expectOne((r) => r.url.includes('/auth/token/')).flush({ access: 'access-1', refresh: 'refresh-1' });
    http.expectOne((r) => r.url.includes('/users/me/')).flush(USER);
    // The session service starts its timer from an effect on the
    // authentication signal. A running application flushes effects on its next
    // change-detection pass; a test has to ask for one.
    TestBed.flushEffects();
  }

  // 1. User logs in successfully.
  it('signs the user in and holds the session in the tab', () => {
    signIn();

    expect(auth.isAuthenticated()).toBeTrue();
    expect(auth.accessToken).toBe('access-1');
  });

  // 8. Closing the tab must leave no persistent client authentication state.
  it('stores tokens in sessionStorage and never in localStorage', () => {
    signIn();

    expect(sessionStorage.getItem(ACCESS_KEY)).toBe('access-1');
    expect(sessionStorage.getItem(REFRESH_KEY)).toBe('refresh-1');
    // localStorage would outlive the tab; sessionStorage is discarded with it.
    expect(localStorage.getItem(ACCESS_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });

  // 9. Opening the app again after the tab closed requires a login.
  it('restores nothing when the tab-scoped storage is empty', () => {
    signIn();
    // A new tab starts with empty sessionStorage; this is that state.
    sessionStorage.clear();

    let restored: User | null | undefined;
    auth.bootstrap().subscribe((user) => (restored = user));

    expect(restored).toBeNull();
    http.expectNone((r) => r.url.includes('/users/me/'));
  });

  it('discards a token left behind by the previous persistent build', () => {
    localStorage.setItem(ACCESS_KEY, 'stale-access');
    localStorage.setItem(REFRESH_KEY, 'stale-refresh');

    auth.bootstrap().subscribe();

    // A credential that outlived its tab is cleared, not honoured.
    expect(localStorage.getItem(ACCESS_KEY)).toBeNull();
    expect(localStorage.getItem(REFRESH_KEY)).toBeNull();
  });

  // 3. A normal reload keeps a valid session.
  it('restores the session from tab storage on reload', () => {
    signIn();

    // A reload builds a fresh service over the same sessionStorage.
    const reloaded = new AuthService(TestBed.inject(HttpTestingController) as never);
    expect(sessionStorage.getItem(ACCESS_KEY)).toBe('access-1');
    expect(reloaded.accessToken).toBe('access-1');
  });

  it('continues the same countdown across a reload rather than restarting it', () => {
    signIn();
    const recordedAt = Number(sessionStorage.getItem(LAST_ACTIVITY_KEY));
    expect(recordedAt).toBeGreaterThan(0);

    // Starting again (as a reload does) must not grant a fresh idle window.
    session.start();
    expect(Number(sessionStorage.getItem(LAST_ACTIVITY_KEY))).toBe(recordedAt);
  });

  // 4. Inactivity signs the user out.
  it('signs the user out after the configured idle period', fakeAsync(() => {
    signIn();

    tick(environment.sessionInactivityTimeoutMinutes * 60_000 + 1_000);
    http.match((r) => r.url.includes('/auth/logout/')).forEach((r) => r.flush({}));

    expect(auth.isAuthenticated()).toBeFalse();
    expect(auth.accessToken).toBeNull();
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
    expect(session.endReason()).toBe('inactivity');
  }));

  it('does not sign the user out while they are active', fakeAsync(() => {
    signIn();
    const timeout = environment.sessionInactivityTimeoutMinutes * 60_000;

    // Three quarters of the way there, the user does something.
    tick(timeout * 0.75);
    document.dispatchEvent(new Event('keydown'));
    tick(timeout * 0.75);

    expect(auth.isAuthenticated()).toBeTrue();

    // And from that activity the full window starts again.
    tick(timeout);
    http.match((r) => r.url.includes('/auth/logout/')).forEach((r) => r.flush({}));
    expect(auth.isAuthenticated()).toBeFalse();
  }));

  it('throttles activity recording instead of writing on every event', fakeAsync(() => {
    signIn();

    // The first event after the timer starts does record — that is the point
    // of watching for activity. What the throttle governs is the flood behind
    // it: `mousemove` alone fires dozens of times a second.
    tick(100);
    document.dispatchEvent(new Event('mousemove'));
    const afterFirst = Number(sessionStorage.getItem(LAST_ACTIVITY_KEY));

    tick(100);
    for (let i = 0; i < 50; i += 1) {
      document.dispatchEvent(new Event('mousemove'));
    }

    // Fifty more events inside the throttle window cost nothing.
    expect(Number(sessionStorage.getItem(LAST_ACTIVITY_KEY))).toBe(afterFirst);

    // Past the window, activity is recorded again.
    tick(6_000);
    document.dispatchEvent(new Event('mousemove'));
    expect(Number(sessionStorage.getItem(LAST_ACTIVITY_KEY))).toBeGreaterThan(afterFirst);

    tick(environment.sessionInactivityTimeoutMinutes * 60_000 + 1_000);
    http.match(() => true).forEach((r) => r.flush({}));
  }));

  it('makes no API call merely because the user moved the mouse', fakeAsync(() => {
    signIn();

    tick(10_000);
    document.dispatchEvent(new Event('mousemove'));
    document.dispatchEvent(new Event('scroll'));

    // Activity is local bookkeeping only.
    http.expectNone(() => true);
    tick(environment.sessionInactivityTimeoutMinutes * 60_000 + 1_000);
    http.match(() => true).forEach((r) => r.flush({}));
  }));

  // 7. Explicit logout clears everything.
  it('clears the session on an explicit logout', () => {
    signIn();

    session.logout();
    http.expectOne((r) => r.url.includes('/auth/logout/')).flush({});

    expect(auth.isAuthenticated()).toBeFalse();
    expect(sessionStorage.getItem(ACCESS_KEY)).toBeNull();
    expect(sessionStorage.getItem(REFRESH_KEY)).toBeNull();
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
  });

  it('still clears the session when the logout call fails', () => {
    signIn();

    session.logout();
    http.expectOne((r) => r.url.includes('/auth/logout/')).error(new ProgressEvent('offline'));

    // A logout button that does nothing when offline would be worse than
    // useless; the backend expires the token on its own schedule regardless.
    expect(auth.isAuthenticated()).toBeFalse();
    expect(sessionStorage.getItem(ACCESS_KEY)).toBeNull();
  });

  // 5. An expired access token is refreshed transparently.
  it('refreshes an expired access token and retries the request', () => {
    signIn();

    let delivered: unknown;
    auth.fetchCurrentUser().subscribe((user) => (delivered = user));

    http.expectOne((r) => r.url.includes('/users/me/')).flush(
      { detail: 'token not valid' }, { status: 401, statusText: 'Unauthorized' },
    );
    http.expectOne((r) => r.url.includes('/auth/token/refresh/')).flush(
      { access: 'access-2', refresh: 'refresh-2' },
    );
    http.expectOne((r) => r.url.includes('/users/me/')).flush(USER);

    expect(delivered).toEqual(USER);
    expect(auth.accessToken).toBe('access-2');
    // Refreshing is not a session ending: the user is never interrupted.
    expect(router.navigate).not.toHaveBeenCalled();
  });

  // 6. An expired refresh token ends the session.
  it('ends the session when the refresh token is rejected', () => {
    signIn();

    auth.fetchCurrentUser().subscribe({ next: () => undefined, error: () => undefined });
    http.expectOne((r) => r.url.includes('/users/me/')).flush(
      { detail: 'token not valid' }, { status: 401, statusText: 'Unauthorized' },
    );
    http.expectOne((r) => r.url.includes('/auth/token/refresh/')).flush(
      { detail: 'Token is blacklisted' }, { status: 401, statusText: 'Unauthorized' },
    );

    expect(auth.isAuthenticated()).toBeFalse();
    expect(sessionStorage.getItem(ACCESS_KEY)).toBeNull();
    expect(router.navigate).toHaveBeenCalledWith(['/login']);
    expect(session.endReason()).toBe('expired');
  });

  it('ends the session when a request is rejected and there is nothing to refresh with', () => {
    signIn();
    sessionStorage.removeItem(REFRESH_KEY);

    auth.fetchCurrentUser().subscribe({ next: () => undefined, error: () => undefined });
    http.expectOne((r) => r.url.includes('/users/me/')).flush(
      { detail: 'token not valid' }, { status: 401, statusText: 'Unauthorized' },
    );

    expect(auth.isAuthenticated()).toBeFalse();
    expect(session.endReason()).toBe('expired');
  });

  // 10. Nothing is left that could still reach a protected endpoint.
  it('leaves no token behind that a later request could use', () => {
    signIn();

    session.logout();
    http.expectOne((r) => r.url.includes('/auth/logout/')).flush({});

    auth.fetchCurrentUser().subscribe({ next: () => undefined, error: () => undefined });
    const request = http.expectOne((r) => r.url.includes('/users/me/'));
    expect(request.request.headers.has('Authorization')).toBeFalse();
    request.flush({ detail: 'unauthenticated' }, { status: 401, statusText: 'Unauthorized' });
  });

  // 11. Multiple tabs behave consistently.
  //
  // Not fakeAsync: BroadcastChannel delivery is a real browser task, and
  // `tick()` only drains the fake timer queue. Faking it would test the mock
  // rather than the mechanism.
  it('signs this tab out when another tab announces a logout', (done) => {
    signIn();

    // A duplicated tab inherits a copy of sessionStorage, so a second tab can
    // be holding the same session. When one signs out, the other must not go
    // on using it.
    const channel = new BroadcastChannel('ssepams_session');
    channel.postMessage({ type: 'logout' });

    setTimeout(() => {
      channel.close();

      expect(auth.isAuthenticated()).toBeFalse();
      expect(sessionStorage.getItem(ACCESS_KEY)).toBeNull();
      expect(session.endReason()).toBe('logged-out-elsewhere');
      // No second blacklist call: the tab that signed out already made it.
      http.expectNone((r) => r.url.includes('/auth/logout/'));
      done();
    }, 50);
  });

  it('ignores a logout announcement when this tab is not signed in', (done) => {
    const channel = new BroadcastChannel('ssepams_session');
    channel.postMessage({ type: 'logout' });

    setTimeout(() => {
      channel.close();
      // Nothing to end, and no spurious trip to the login page.
      expect(session.endReason()).toBeNull();
      expect(router.navigate).not.toHaveBeenCalled();
      done();
    }, 50);
  });

  it('stops watching for activity once the session has ended', fakeAsync(() => {
    signIn();
    session.logout();
    http.expectOne((r) => r.url.includes('/auth/logout/')).flush({});
    TestBed.flushEffects();

    // No timer should remain that could fire against a signed-out session.
    tick(environment.sessionInactivityTimeoutMinutes * 60_000 * 2);
    http.expectNone((r) => r.url.includes('/auth/logout/'));
    expect(sessionStorage.getItem(LAST_ACTIVITY_KEY)).toBeNull();
  }));
});

describe('Session lifecycle — navigation', () => {
  /**
   * Requirement 36.3: moving around the application is not a session event.
   * The timer is owned by the session service and keyed to authentication, so
   * routing cannot end a session — asserted here by routing repeatedly and
   * checking the session survives.
   */
  let auth: AuthService;
  let http: HttpTestingController;

  // Real (if empty) routes, so navigation genuinely resolves rather than
  // failing before it can prove anything about the session.
  const ROUTES = [
    { path: 'dashboard', children: [] },
    { path: 'student/events', children: [] },
    { path: 'reports', children: [] },
    { path: 'login', children: [] },
  ];

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter(ROUTES),
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    auth = TestBed.inject(AuthService);
    TestBed.inject(SessionService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => sessionStorage.clear());

  // 2. Normal navigation never signs the user out.
  it('keeps the session across repeated navigation', fakeAsync(() => {
    auth.login({ username: 'stu1', password: 'pw' }).subscribe();
    http.expectOne((r) => r.url.includes('/auth/token/')).flush({ access: 'a', refresh: 'r' });
    http.expectOne((r) => r.url.includes('/users/me/')).flush(USER);
    TestBed.flushEffects();

    const router = TestBed.inject(Router);
    for (const url of ['/dashboard', '/student/events', '/reports', '/dashboard']) {
      router.navigateByUrl(url);
      tick();
    }

    expect(auth.isAuthenticated()).toBeTrue();
    expect(auth.accessToken).toBe('a');
    http.expectNone((r) => r.url.includes('/auth/logout/'));
  }));
});
