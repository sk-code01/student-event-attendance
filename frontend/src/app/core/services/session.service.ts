import { DOCUMENT } from '@angular/common';
import { Injectable, effect, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { environment } from '../../../environments/environment';
import { AuthService } from './auth.service';

/** Why a session ended, so the login page can say something useful. */
export type SessionEndReason = 'inactivity' | 'expired' | 'logged-out-elsewhere' | null;

/**
 * Events that count as the user being present.
 *
 * Deliberately a small set of real interactions. They are all registered
 * passively and their handler does nothing but note the time, so even
 * `mousemove` and `scroll` cost almost nothing — and none of them ever causes
 * a network request (requirement 36.6).
 */
const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'touchstart', 'scroll', 'wheel'] as const;

/**
 * The shortest interval between two recorded activity timestamps.
 *
 * `mousemove` fires dozens of times a second; writing the clock on every one
 * of them would be pure waste. Five seconds is far finer than any sane
 * inactivity limit, so throttling this hard costs no accuracy.
 */
const ACTIVITY_THROTTLE_MS = 5_000;

/** Survives a reload of the same tab, so the countdown continues rather than restarting. */
const LAST_ACTIVITY_KEY = 'ssepams_last_activity_at';

/** Cross-tab logout signalling. */
const BROADCAST_CHANNEL = 'ssepams_session';

@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly document = inject(DOCUMENT);

  /** Read by the login page to explain why the user landed back there. */
  private readonly _endReason = signal<SessionEndReason>(null);
  readonly endReason = this._endReason.asReadonly();

  private timerId: ReturnType<typeof setTimeout> | null = null;
  private lastRecordedAt = 0;
  private listening = false;
  private channel: BroadcastChannel | null = null;

  private readonly boundActivity = () => this.recordActivity();

  constructor() {
    this.openChannel();

    // The timer follows authentication rather than any one component: it
    // starts at login, stops at logout, and is unaffected by navigation
    // (requirement 36.3 — a route change is not a session event).
    effect(() => {
      if (this.auth.isAuthenticated()) {
        this.start();
      } else {
        this.stop();
      }
    });
  }

  get timeoutMs(): number {
    return environment.sessionInactivityTimeoutMinutes * 60_000;
  }

  /** Begins watching for inactivity. Safe to call repeatedly. */
  start(): void {
    if (!this.listening) {
      for (const eventName of ACTIVITY_EVENTS) {
        this.document.addEventListener(eventName, this.boundActivity, { passive: true });
      }
      this.listening = true;
    }

    // A reload keeps the original countdown: without this, refreshing the page
    // would silently grant a fresh idle window every time.
    if (this.readLastActivity() === null) {
      this.writeLastActivity(Date.now());
    }
    this.schedule();
  }

  stop(): void {
    if (this.listening) {
      for (const eventName of ACTIVITY_EVENTS) {
        this.document.removeEventListener(eventName, this.boundActivity);
      }
      this.listening = false;
    }
    this.clearTimer();
    this.clearLastActivity();
  }

  clearEndReason(): void {
    this._endReason.set(null);
  }

  /**
   * Explicit sign-out. Tells the backend to blacklist the refresh token, clears
   * this tab, and tells any other tab of this application to do the same —
   * otherwise a duplicated tab (which inherits a copy of sessionStorage) would
   * go on using a session the user believes they ended.
   */
  logout(reason: SessionEndReason = null): void {
    this.announce('logout');
    this.auth.logout().subscribe({
      next: () => this.finish(reason),
      // The blacklist call failing must not leave the client signed in; the
      // backend still expires the token on its own schedule.
      error: () => this.finish(reason),
    });
  }

  /**
   * Ends the session because the backend rejected it — an expired or revoked
   * token. No logout call: there is nothing valid left to blacklist.
   */
  endBecauseRejected(): void {
    this.auth.clearSession();
    this.finish('expired');
  }

  // ---------------------------------------------------------------- internals

  private recordActivity(): void {
    const now = Date.now();
    if (now - this.lastRecordedAt < ACTIVITY_THROTTLE_MS) {
      return;
    }
    this.lastRecordedAt = now;
    this.writeLastActivity(now);
    this.schedule();
  }

  private schedule(): void {
    this.clearTimer();
    const remaining = this.remainingMs();
    if (remaining <= 0) {
      this.expire();
      return;
    }
    this.timerId = setTimeout(() => this.onTimer(), remaining);
  }

  private onTimer(): void {
    // Re-checked against the clock rather than trusted: a background tab's
    // timers are throttled, and the machine may have been asleep, so the timer
    // firing is a prompt to look at the time, not proof that time has passed.
    if (this.remainingMs() > 0) {
      this.schedule();
      return;
    }
    this.expire();
  }

  private remainingMs(): number {
    const last = this.readLastActivity();
    if (last === null) {
      return this.timeoutMs;
    }
    return last + this.timeoutMs - Date.now();
  }

  private expire(): void {
    if (!this.auth.isAuthenticated() && !this.auth.accessToken) {
      return;
    }
    this.logout('inactivity');
  }

  private finish(reason: SessionEndReason): void {
    this.stop();
    this._endReason.set(reason);
    this.router.navigate(['/login']);
  }

  // ------------------------------------------------------------- other tabs

  private openChannel(): void {
    try {
      this.channel = new BroadcastChannel(BROADCAST_CHANNEL);
      this.channel.onmessage = (event: MessageEvent<{ type?: string }>) => {
        if (event.data?.type !== 'logout' || !this.auth.isAuthenticated()) {
          return;
        }
        // Another tab signed out. Clear locally without calling the backend
        // again — the refresh token there has already been blacklisted.
        this.auth.clearSession();
        this.finish('logged-out-elsewhere');
      };
    } catch {
      // BroadcastChannel is unavailable. Each tab still holds its own
      // session-scoped tokens, so this only costs the cross-tab courtesy.
      this.channel = null;
    }
  }

  private announce(type: 'logout'): void {
    try {
      this.channel?.postMessage({ type });
    } catch {
      /* no-op */
    }
  }

  // ---------------------------------------------------------------- storage

  private readLastActivity(): number | null {
    try {
      const raw = window.sessionStorage.getItem(LAST_ACTIVITY_KEY);
      if (!raw) {
        return null;
      }
      const value = Number(raw);
      return Number.isFinite(value) ? value : null;
    } catch {
      return null;
    }
  }

  private writeLastActivity(at: number): void {
    try {
      window.sessionStorage.setItem(LAST_ACTIVITY_KEY, String(at));
    } catch {
      /* no-op */
    }
  }

  private clearLastActivity(): void {
    try {
      window.sessionStorage.removeItem(LAST_ACTIVITY_KEY);
    } catch {
      /* no-op */
    }
  }

  private clearTimer(): void {
    if (this.timerId !== null) {
      clearTimeout(this.timerId);
      this.timerId = null;
    }
  }
}
