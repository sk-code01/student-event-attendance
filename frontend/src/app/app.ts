import { DOCUMENT } from '@angular/common';
import { Component, HostListener, computed, effect, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';

import { NAVIGATION, ROLE_HOME, ROLE_LABEL, NavSection } from './core/navigation';
import { Role } from './core/models/user.model';
import { AuthService } from './core/services/auth.service';
import { NotificationService } from './core/services/notification.service';
import { SessionService } from './core/services/session.service';
import { ThemeService } from './core/services/theme.service';
import { ToastService } from './core/services/toast.service';
import { IconComponent } from './shared/icon/icon.component';
import { NotificationBellComponent } from './shared/notification-bell/notification-bell.component';
import { ToastContainerComponent } from './shared/toast/toast-container.component';

const SIDEBAR_KEY = 'seams_sidebar_collapsed';

/**
 * SEAMS-AI application shell.
 *
 * One shell serves all four roles. The role does not change the *structure*
 * — sidebar, header, content — it changes the tokens the structure renders
 * with (`data-role` on <html>) and which navigation sections appear. That is
 * what keeps four visibly distinct experiences inside one codebase rather
 * than four near-duplicate layouts that drift apart.
 *
 * The shell is only drawn for an authenticated user; login and register
 * render standalone through the same <router-outlet>.
 */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    IconComponent,
    NotificationBellComponent,
    ToastContainerComponent,
  ],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  private readonly document = inject(DOCUMENT);
  private readonly router = inject(Router);
  private readonly toast = inject(ToastService);
  private readonly sessionService = inject(SessionService);

  protected readonly authService = inject(AuthService);
  protected readonly themeService = inject(ThemeService);
  protected readonly notificationService = inject(NotificationService);

  /** Desktop: icon-rail vs full sidebar. Persisted — it is a workspace preference. */
  readonly collapsed = signal(this.readCollapsed());
  /** Mobile: the full-screen menu. Never persisted. */
  readonly mobileNavOpen = signal(false);
  readonly profileOpen = signal(false);

  readonly role = computed<Role | null>(() => this.authService.currentUser()?.role ?? null);
  readonly roleLabel = computed(() => (this.role() ? ROLE_LABEL[this.role()!] : ''));
  readonly sections = computed<NavSection[]>(() => (this.role() ? NAVIGATION[this.role()!] : []));
  readonly homeRoute = computed(() => (this.role() ? ROLE_HOME[this.role()!] : '/dashboard'));

  readonly initials = computed(() => {
    const user = this.authService.currentUser();
    if (!user) {
      return '';
    }
    const name = `${user.username ?? ''}`.trim();
    return name.slice(0, 2).toUpperCase();
  });

  /** Changes through the day, so the greeting is not stale on a long session. */
  readonly greeting = computed(() => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  });

  constructor() {
    // One place decides whether notification polling runs: authentication
    // state. Logging in starts the single app-wide timer; logging out (or a
    // refresh-token failure that clears the user) stops it and zeroes the
    // badge, so the next user of this browser never inherits a stale count.
    effect(() => {
      if (this.authService.isAuthenticated()) {
        this.notificationService.startPolling();
      } else {
        this.notificationService.stopPolling();
      }
    });

    // The role drives every accent, radius and glass decision in the
    // stylesheet. Writing it to <html> once here means no component ever has
    // to branch on role for styling.
    effect(() => {
      this.document.documentElement.setAttribute('data-role', this.role() ?? 'NONE');
    });

    // Close transient surfaces on navigation: a menu left open over a new
    // page is disorienting, and on mobile it would cover the destination.
    this.router.events.pipe(filter((event) => event instanceof NavigationEnd)).subscribe(() => {
      this.mobileNavOpen.set(false);
      this.profileOpen.set(false);
    });
  }

  // ------------------------------------------------------------- chrome

  toggleSidebar(): void {
    this.collapsed.update((value) => {
      const next = !value;
      this.writeCollapsed(next);
      return next;
    });
  }

  toggleMobileNav(): void {
    this.mobileNavOpen.update((open) => !open);
  }

  closeMobileNav(): void {
    this.mobileNavOpen.set(false);
  }

  toggleProfile(): void {
    this.profileOpen.update((open) => !open);
  }

  cycleTheme(): void {
    const next = this.themeService.cycle();
    const label = next === 'system' ? 'System' : next === 'dark' ? 'Dark' : 'Light';
    this.toast.info(`${label} theme`, next === 'system' ? 'Following your device setting.' : undefined);
  }

  themeIcon(): string {
    switch (this.themeService.preference()) {
      case 'light': return 'sun';
      case 'dark': return 'moon';
      default: return 'monitor';
    }
  }

  themeLabel(): string {
    switch (this.themeService.preference()) {
      case 'light': return 'Theme: Light. Switch to dark.';
      case 'dark': return 'Theme: Dark. Switch to system.';
      default: return 'Theme: System. Switch to light.';
    }
  }

  /** Escape closes whatever transient surface is open, innermost first. */
  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.profileOpen()) {
      this.profileOpen.set(false);
    } else if (this.mobileNavOpen()) {
      this.mobileNavOpen.set(false);
    }
  }

  /** A click anywhere outside the profile menu dismisses it. */
  @HostListener('document:click', ['$event'])
  onDocumentClick(event: MouseEvent): void {
    if (!this.profileOpen()) {
      return;
    }
    const target = event.target as HTMLElement | null;
    if (target && !target.closest('[data-profile-menu]')) {
      this.profileOpen.set(false);
    }
  }

  // ------------------------------------------------------------ actions

  logout(): void {
    this.profileOpen.set(false);
    this.notificationService.stopPolling();
    // Routed through SessionService so the refresh token is blacklisted, this
    // tab is cleared, and any other open tab of the application is told to
    // sign out too — a duplicated tab inherits a copy of sessionStorage and
    // would otherwise keep using a session the user believes they ended.
    // It always clears locally, even if the server call fails: a logout button
    // that silently does nothing when offline would be worse than useless.
    this.toast.success('Signed out', 'You have been signed out of SEAMS-AI.');
    this.sessionService.logout();
  }

  // ------------------------------------------------------------ storage

  private readCollapsed(): boolean {
    try {
      return this.document.defaultView?.localStorage.getItem(SIDEBAR_KEY) === '1';
    } catch {
      return false;
    }
  }

  private writeCollapsed(value: boolean): void {
    try {
      this.document.defaultView?.localStorage.setItem(SIDEBAR_KEY, value ? '1' : '0');
    } catch {
      /* A non-persisted preference is an acceptable degradation. */
    }
  }
}
