import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';

import { AppNotification } from '../../core/models/notification.model';
import { NotificationService } from '../../core/services/notification.service';

/**
 * The full notification list, backend-paginated. Every authenticated role
 * uses this same page — the backend scopes it to the recipient, so there is
 * nothing role-specific to render.
 *
 * Notifications cannot be deleted here: this phase preserves history, and the
 * API offers no destroy action.
 */
@Component({
  selector: 'app-notifications-page',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './notifications-page.component.html',
})
export class NotificationsPageComponent implements OnInit {
  // See NotificationBellComponent: inject() is required because the
  // unreadCount field initializer below runs before parameter properties.
  private readonly notificationService = inject(NotificationService);
  private readonly router = inject(Router);

  readonly notifications = signal<AppNotification[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly unreadOnly = signal(false);
  readonly page = signal(1);
  readonly totalCount = signal(0);
  readonly hasNext = signal(false);
  readonly hasPrevious = signal(false);

  readonly unreadCount = inject(NotificationService).unreadCount;

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    this.notificationService.list(this.page(), this.unreadOnly()).subscribe({
      next: (result) => {
        this.notifications.set(result.results);
        this.totalCount.set(result.count);
        this.hasNext.set(result.next !== null);
        this.hasPrevious.set(result.previous !== null);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load notifications.');
        this.loading.set(false);
      },
    });
  }

  toggleUnreadOnly(): void {
    this.unreadOnly.update((value) => !value);
    this.page.set(1);
    this.load();
  }

  nextPage(): void {
    if (this.hasNext()) {
      this.page.update((p) => p + 1);
      this.load();
    }
  }

  previousPage(): void {
    if (this.hasPrevious()) {
      this.page.update((p) => Math.max(1, p - 1));
      this.load();
    }
  }

  markRead(notification: AppNotification): void {
    if (notification.is_read) {
      return;
    }
    this.notificationService.markRead(notification.id).subscribe({
      next: (updated) =>
        this.notifications.update((list) => list.map((n) => (n.id === updated.id ? updated : n))),
      error: () => this.errorMessage.set('Unable to mark this notification as read.'),
    });
  }

  markAllRead(): void {
    this.notificationService.markAllRead().subscribe({
      next: () => this.load(),
      error: () => this.errorMessage.set('Unable to mark all as read.'),
    });
  }

  /** Marks read then navigates. `action_route` is backend-validated as an
   * internal path, so it is safe to pass to the router. */
  open(notification: AppNotification): void {
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
      next: () => navigate(),
      error: () => navigate(),
    });
  }

  badgeClass(type: string): string {
    if (type.endsWith('_APPROVED') || type === 'EVIDENCE_VERIFIED') {
      return 'text-bg-success';
    }
    if (type.endsWith('_REJECTED') || type === 'EVENT_CANCELLED') {
      return 'text-bg-danger';
    }
    if (type === 'EVIDENCE_RESUBMISSION_REQUIRED' || type === 'EVENT_COORDINATOR_OVERRIDE') {
      return 'text-bg-warning';
    }
    return 'text-bg-secondary';
  }
}
