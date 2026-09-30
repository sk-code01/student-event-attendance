import { HttpClient } from '@angular/common/http';
import { Injectable, computed, signal } from '@angular/core';
import { Observable, catchError, of, switchMap, tap, throwError } from 'rxjs';

import { environment } from '../../../environments/environment';
import { ChangePasswordRequest, LoginRequest, RegisterRequest, RegisterResponse, TokenPair } from '../models/auth.model';
import { Role, User } from '../models/user.model';

const ACCESS_TOKEN_KEY = 'ssepams_access_token';
const REFRESH_TOKEN_KEY = 'ssepams_refresh_token';

/**
 * Tokens live in `sessionStorage`, not `localStorage`.
 *
 * sessionStorage is scoped to the browser tab and is discarded by the browser
 * when that tab closes, so an abandoned tab leaves no credential behind — the
 * behaviour requirement 36.2 asks for. It is deliberately not implemented with
 * an unload handler: the browser makes no promise that work started during
 * unload finishes, and none runs at all if the tab is killed or the machine
 * loses power. Storage that the browser itself discards needs no such promise.
 *
 * It still survives a reload of the same tab, which is what keeps requirement
 * 36.4 (a refresh must not sign the user out) true at the same time.
 */
const tokenStorage = (): Storage | null => {
  try {
    return window.sessionStorage;
  } catch {
    // Private browsing or a locked-down browser. The user can still work; the
    // session simply will not survive a reload.
    return null;
  }
};

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly baseUrl = environment.apiBaseUrl;

  private readonly _currentUser = signal<User | null>(null);
  readonly currentUser = this._currentUser.asReadonly();
  readonly isAuthenticated = computed(() => this._currentUser() !== null);

  constructor(private readonly http: HttpClient) {}

  get accessToken(): string | null {
    return this.readStorage(ACCESS_TOKEN_KEY);
  }

  get refreshTokenValue(): string | null {
    return this.readStorage(REFRESH_TOKEN_KEY);
  }

  hasRole(...roles: Role[]): boolean {
    const user = this._currentUser();
    return !!user && roles.includes(user.role);
  }

  /** Called once at app startup to restore a session from a stored access
   * token, if any. Angular never trusts the token payload for role/identity
   * — it always re-fetches /users/me/ from the backend. */
  bootstrap(): Observable<User | null> {
    // Any token from the previous localStorage-backed build is cleared here
    // rather than honoured: it outlived its tab, which is the thing the
    // session-scoped design refuses to allow.
    this.purgeLegacyPersistentTokens();

    if (!this.accessToken) {
      return of(null);
    }
    return this.fetchCurrentUser().pipe(catchError(() => of(null)));
  }

  login(payload: LoginRequest): Observable<User> {
    return this.http.post<TokenPair>(`${this.baseUrl}/auth/token/`, payload).pipe(
      tap((tokens) => this.storeTokens(tokens)),
      switchMap(() => this.fetchCurrentUser()),
    );
  }

  register(payload: RegisterRequest): Observable<RegisterResponse> {
    return this.http.post<RegisterResponse>(`${this.baseUrl}/auth/register/`, payload);
  }

  registrationStatus(username: string): Observable<unknown> {
    return this.http.post(`${this.baseUrl}/auth/registration-status/`, { username });
  }

  fetchCurrentUser(): Observable<User> {
    return this.http.get<User>(`${this.baseUrl}/users/me/`).pipe(
      tap((user) => this._currentUser.set(user)),
    );
  }

  changePassword(payload: ChangePasswordRequest): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`${this.baseUrl}/users/me/password/`, payload);
  }

  refreshAccessToken(): Observable<TokenPair> {
    const refresh = this.refreshTokenValue;
    if (!refresh) {
      return throwError(() => new Error('No refresh token available.'));
    }
    return this.http.post<TokenPair>(`${this.baseUrl}/auth/token/refresh/`, { refresh }).pipe(
      tap((tokens) => this.storeTokens({ access: tokens.access, refresh: tokens.refresh ?? refresh })),
    );
  }

  logout(): Observable<void> {
    const refresh = this.refreshTokenValue;
    const request$ = refresh
      ? this.http.post(`${this.baseUrl}/auth/logout/`, { refresh }).pipe(catchError(() => of(null)))
      : of(null);

    return request$.pipe(
      tap(() => this.clearSession()),
      switchMap(() => of(undefined)),
    );
  }

  clearSession(): void {
    this._currentUser.set(null);
    this.removeStorage(ACCESS_TOKEN_KEY);
    this.removeStorage(REFRESH_TOKEN_KEY);
  }

  private storeTokens(tokens: TokenPair): void {
    this.writeStorage(ACCESS_TOKEN_KEY, tokens.access);
    this.writeStorage(REFRESH_TOKEN_KEY, tokens.refresh);
  }

  private readStorage(key: string): string | null {
    try {
      return tokenStorage()?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }

  private writeStorage(key: string, value: string): void {
    try {
      tokenStorage()?.setItem(key, value);
    } catch {
      /* Storage unavailable (private browsing, etc.) — the session simply
         won't survive a reload. */
    }
  }

  private removeStorage(key: string): void {
    try {
      tokenStorage()?.removeItem(key);
    } catch {
      /* no-op */
    }
  }

  /**
   * Removes tokens left in localStorage by the earlier build.
   *
   * Without this, a credential written before the move would sit on disk
   * indefinitely — readable after the tab closed, which is precisely what
   * requirement 36.2 exists to prevent. Called once at startup.
   */
  purgeLegacyPersistentTokens(): void {
    try {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      localStorage.removeItem(REFRESH_TOKEN_KEY);
    } catch {
      /* no-op */
    }
  }
}
