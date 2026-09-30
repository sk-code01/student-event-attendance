import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ActivityRecord } from '../../core/models/activity.model';
import { ActivityService } from '../../core/services/activity.service';
import { AuthService } from '../../core/services/auth.service';
import { EmptyStateComponent } from '../../shared/empty-state/empty-state.component';

/**
 * The administrative audit trail, backed by the existing AuditLog.
 *
 * Reached by Admin (system-wide) and Event Coordinator (own department). Student and Faculty
 * are refused by the backend with 403 and by the route guard in front of it —
 * the guard is UX only, the backend is the boundary.
 *
 * Nothing is redacted client-side because there is nothing sensitive to
 * redact: AuditLog.record() never stores passwords, tokens, image bytes or
 * GPS values, only a short human description written by the service layer.
 */
@Component({
  selector: 'app-audit-log',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink, EmptyStateComponent],
  templateUrl: './audit-log.component.html',
})
export class AuditLogComponent implements OnInit {
  readonly records = signal<ActivityRecord[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly forbidden = signal(false);
  readonly page = signal(1);
  readonly totalCount = signal(0);
  readonly hasNext = signal(false);
  readonly hasPrevious = signal(false);

  action = '';
  search = '';
  dateFrom = '';
  dateTo = '';

  constructor(
    protected readonly authService: AuthService,
    private readonly activityService: ActivityService,
  ) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.errorMessage.set(null);
    this.forbidden.set(false);
    this.activityService
      .auditTrail({
        action: this.action.trim() || undefined,
        search: this.search.trim() || undefined,
        date_from: this.dateFrom || undefined,
        date_to: this.dateTo || undefined,
        page: this.page(),
      })
      .subscribe({
        next: (result) => {
          this.records.set(result.results);
          this.totalCount.set(result.count);
          this.hasNext.set(result.next !== null);
          this.hasPrevious.set(result.previous !== null);
          this.loading.set(false);
        },
        error: (error: HttpErrorResponse) => {
          this.loading.set(false);
          if (error.status === 403) {
            this.forbidden.set(true);
            this.errorMessage.set('The audit trail is available to Event Coordinator and Admin accounts only.');
            return;
          }
          this.errorMessage.set('Unable to load the audit trail.');
        },
      });
  }

  applyFilters(): void {
    this.page.set(1);
    this.load();
  }

  clearFilters(): void {
    this.action = '';
    this.search = '';
    this.dateFrom = '';
    this.dateTo = '';
    this.applyFilters();
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

  homeRoute(): string {
    return this.authService.currentUser()?.role === 'EVENT_COORDINATOR' ? '/event-coordinator' : '/admin';
  }
}
