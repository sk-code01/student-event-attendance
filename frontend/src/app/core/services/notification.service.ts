import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';

import { environment } from '../../../environments/environment';
import { AppNotification } from '../models/notification.model';
import { Paginated } from '../models/pagination.model';

/**
 * In-app notifications.
 *
 * The unread count lives here as a signal so the bell in the app shell and any
 * page that changes read state share one source of truth — marking something
 * read on the notifications page updates the bell immediately, with no second
 * request and no stale badge.
 *
 * Polling is owned by this service rather than by the bell component, so there
 * is exactly one timer no matter how many components are mounted. It is
 * started explicitly on login and stopped on logout.
 */
@Injectable({ providedIn: 'root' })
export class NotificationService {
  private readonly baseUrl = environment.apiBaseUrl;

  private readonly _unreadCount = signal(0);
  readonly unreadCount = this._unreadCount.asReadonly();

  /** A single timer handle. Guarded so a second start() is a no-op rather
   * than leaking a duplicate interval. */
  private pollHandle: ReturnType<typeof setInterval> | null = null;

  /** 60s: frequent enough that a badge is never badly stale, infrequent
   * enough that it is not an aggressive poll. No WebSocket is introduced —
   * nothing in this phase needs sub-minute latency. */
  static readonly POLL_INTERVAL_MS = 60_000;

  constructor(private readonly http: HttpClient) {}

  list(page = 1, unreadOnly = false): Observable<Paginated<AppNotification>> {
    const params: Record<string, string> = { page: String(page) };
    if (unreadOnly) {
      params['unread'] = 'true';
    }
    return this.http.get<Paginated<AppNotification>>(`${this.baseUrl}/notifications/`, { params });
  }

  get(id: number): Observable<AppNotification> {
    return this.http.get<AppNotification>(`${this.baseUrl}/notifications/${id}/`);
  }

  /** Server sets read_at from its own clock; nothing is sent. */
  markRead(id: number): Observable<AppNotification> {
    return this.http.post<AppNotification>(`${this.baseUrl}/notifications/${id}/read/`, {}).pipe(
      tap(() => this._unreadCount.update((n) => Math.max(0, n - 1))),
    );
  }

  markAllRead(): Observable<{ marked_read: number }> {
    return this.http.post<{ marked_read: number }>(`${this.baseUrl}/notifications/read-all/`, {}).pipe(
      tap(() => this._unreadCount.set(0)),
    );
  }

  refreshUnreadCount(): Observable<{ unread: number }> {
    return this.http.get<{ unread: number }>(`${this.baseUrl}/notifications/unread-count/`).pipe(
      tap((result) => this._unreadCount.set(result.unread)),
    );
  }

  /** Called once the user is authenticated. Safe to call repeatedly. */
  startPolling(): void {
    if (this.pollHandle !== null) {
      return;
    }
    this.refreshUnreadCount().subscribe({ error: () => undefined });
    this.pollHandle = setInterval(
      () => this.refreshUnreadCount().subscribe({ error: () => undefined }),
      NotificationService.POLL_INTERVAL_MS,
    );
  }

  /** Called on logout. Clears the timer and zeroes the badge so the next user
   * of this browser never sees the previous user's count. */
  stopPolling(): void {
    if (this.pollHandle !== null) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
    this._unreadCount.set(0);
  }
}
