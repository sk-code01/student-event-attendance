import { DatePipe } from '@angular/common';
import { Component, HostListener, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { AppNotification } from '../../core/models/notification.model';
import { NotificationService } from '../../core/services/notification.service';
import { IconComponent } from '../icon/icon.component';

/**
 * The shared notification indicator for the authenticated app shell. One
 * component reused by every role — there is no per-role variant, because a
 * notification is already scoped to its recipient by the backend.
 *
 * The unread badge reads the NotificationService signal rather than holding
 * its own count, so it stays in step with the notifications page without a
 * second request. Polling is owned by the service (one timer app-wide), not
 * started here.
 */
@Component({
  selector: 'app-notification-bell',
  standalone: true,
  imports: [DatePipe, RouterLink, IconComponent],
  templateUrl: './notification-bell.component.html',
  styleUrl: './notification-bell.component.css',
})
export class NotificationBellComponent {
  // inject() rather than a constructor parameter property: field
  // initializers run before parameter properties are assigned, so
  // `notificationService.unreadCount` below would read undefined.
  private readonly notificationService = inject(NotificationService);
  private readonly router = inject(Router);

  readonly open = signal(false);
  readonly recent = signal<AppNotification[]>([]);
  readonly loading = signal(false);
  readonly errorMessage = signal<string | null>(null);

  readonly unreadCount = this.notificationService.unreadCount;

  toggle(): void {
    const next = !this.open();
    this.open.set(next);
    if (next) {
      this.loadRecent();
    }
  }

  close(): void {
    this.open.set(false);
  }

  /** A click anywhere outside the panel dismisses it, matching the profile
   *  menu's behaviour so the two header surfaces feel the same. */
  @HostListener('document:click', ['$event'])
  protected onDocumentClick(event: MouseEvent): void {
    if (!this.open()) {
      return;
    }
    const target = event.target as HTMLElement | null;
    if (target && !target.closest('[data-notification-bell]')) {
      this.close();
    }
  }

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    this.close();
  }

  private loadRecent(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    this.notificationService.list(1).subscribe({
      next: (page) => {
        this.recent.set(page.results.slice(0, 6));
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load notifications.');
        this.loading.set(false);
      },
    });
  }

  /** Marks read, then navigates to the notification's internal route. The
   * route came from the backend, which only stores single-slash internal
   * paths, so this can never become an external redirect. */
  openNotification(notification: AppNotification): void {
    this.close();
    const navigate = () => {
      if (notification.action_route) {
        this.router.navigateByUrl(notification.action_route);
      }
    };
    if (notification.is_read) {
      navigate();
      return;
    }
    this.notificationService.markRead(notification.id).subscribe({
      next: () => {
        this.recent.update((list) =>
          list.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n)),
        );
        navigate();
      },
      error: () => navigate(),
    });
  }

  markAllRead(): void {
    this.notificationService.markAllRead().subscribe({
      next: () => this.recent.update((list) => list.map((n) => ({ ...n, is_read: true }))),
      error: () => this.errorMessage.set('Unable to mark all as read.'),
    });
  }
}
