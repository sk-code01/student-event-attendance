import { HttpErrorResponse, HttpEvent, HttpHandlerFn, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { BehaviorSubject, Observable, catchError, filter, switchMap, take, throwError } from 'rxjs';

import { AuthService } from '../services/auth.service';
import { SessionService } from '../services/session.service';

/** Endpoints that never carry (or need) an Authorization header. */
const PUBLIC_PATHS = ['/auth/token/', '/auth/register/', '/auth/registration-status/'];

// Module-scoped so every request sharing this interceptor instance sees the
// same in-flight refresh, instead of firing one refresh call per 401.
let isRefreshing = false;
const refreshedAccessToken$ = new BehaviorSubject<string | null>(null);

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const session = inject(SessionService);

  const isPublicPath = PUBLIC_PATHS.some((path) => req.url.includes(path));
  const token = authService.accessToken;

  const authorizedReq = token && !isPublicPath
    ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } })
    : req;

  return next(authorizedReq).pipe(
    catchError((error: unknown) => {
      const isUnauthorized = error instanceof HttpErrorResponse && error.status === 401;
      const isRefreshCall = req.url.includes('/auth/token/refresh/');

      if (isUnauthorized && !isPublicPath && !isRefreshCall) {
        return handleUnauthorized(req, next, authService, session);
      }
      return throwError(() => error);
    }),
  );
};

function handleUnauthorized(
  req: HttpRequest<unknown>,
  next: HttpHandlerFn,
  authService: AuthService,
  session: SessionService,
): Observable<HttpEvent<unknown>> {
  if (!authService.refreshTokenValue) {
    // Nothing left to refresh with. Ending through the session service rather
    // than clearing here keeps one path for "the backend no longer accepts
    // this session", so the user is always told why they are back at login.
    session.endBecauseRejected();
    return throwError(() => new Error('Session expired. Please log in again.'));
  }

  if (!isRefreshing) {
    isRefreshing = true;
    refreshedAccessToken$.next(null);

    return authService.refreshAccessToken().pipe(
      switchMap((tokens) => {
        isRefreshing = false;
        refreshedAccessToken$.next(tokens.access);
        return next(req.clone({ setHeaders: { Authorization: `Bearer ${tokens.access}` } }));
      }),
      catchError((refreshError: unknown) => {
        // The refresh token is expired, rotated away or blacklisted. This is
        // the end of the session, not a retryable error.
        isRefreshing = false;
        session.endBecauseRejected();
        return throwError(() => refreshError);
      }),
    );
  }

  // A refresh is already in flight for another request — wait for it
  // instead of triggering a second one.
  return refreshedAccessToken$.pipe(
    filter((token): token is string => token !== null),
    take(1),
    switchMap((token) => next(req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }))),
  );
}
