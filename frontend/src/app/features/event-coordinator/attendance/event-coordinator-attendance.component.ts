import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { Attendance } from '../../../core/models/attendance.model';
import { AttendanceService } from '../../../core/services/attendance.service';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';

/**
 * Event Coordinator attendance approval queue, department-scoped by the backend (this
 * component never filters by department itself — the server's queryset is the
 * boundary). Rejection requires a reason, and the action buttons are disabled
 * while a decision is in flight so a double click cannot fire twice; the
 * backend's row lock is the real guarantee.
 */
@Component({
  selector: 'app-event-coordinator-attendance',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink, EmptyStateComponent],
  templateUrl: './event-coordinator-attendance.component.html',
})
export class EventCoordinatorAttendanceComponent implements OnInit {
  readonly records = signal<Attendance[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly actioningId = signal<number | null>(null);
  readonly rejectingId = signal<number | null>(null);
  rejectionReason = '';

  readonly pending = computed(() => this.records().filter((r) => r.status === 'PENDING'));
  readonly decided = computed(() => this.records().filter((r) => r.status !== 'PENDING'));

  constructor(private readonly attendanceService: AttendanceService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.attendanceService.list().subscribe({
      next: (page) => {
        this.records.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load attendance requests.');
        this.loading.set(false);
      },
    });
  }

  approve(record: Attendance): void {
    if (this.actioningId() !== null) {
      return;
    }
    this.actioningId.set(record.id);
    this.errorMessage.set(null);
    this.attendanceService.approve(record.id).subscribe({
      next: (updated) => this.applyDecision(updated),
      error: (error: HttpErrorResponse) => this.handleError(error, 'Unable to approve this request.'),
    });
  }

  startReject(record: Attendance): void {
    this.rejectingId.set(record.id);
    this.rejectionReason = '';
    this.errorMessage.set(null);
  }

  cancelReject(): void {
    this.rejectingId.set(null);
    this.rejectionReason = '';
  }

  confirmReject(record: Attendance): void {
    if (!this.rejectionReason.trim() || this.actioningId() !== null) {
      return;
    }
    this.actioningId.set(record.id);
    this.attendanceService.reject(record.id, this.rejectionReason.trim()).subscribe({
      next: (updated) => {
        this.rejectingId.set(null);
        this.rejectionReason = '';
        this.applyDecision(updated);
      },
      error: (error: HttpErrorResponse) => this.handleError(error, 'Unable to reject this request.'),
    });
  }

  badgeClass(status: string): string {
    if (status === 'APPROVED') {
      return 'text-bg-success';
    }
    return status === 'REJECTED' ? 'text-bg-danger' : 'text-bg-info';
  }

  /** Replaces the row in place rather than reloading the page, so the decided
   * record stays visible with its new status and its history is preserved. */
  private applyDecision(updated: Attendance): void {
    this.actioningId.set(null);
    this.records.update((list) => list.map((r) => (r.id === updated.id ? updated : r)));
  }

  private handleError(error: HttpErrorResponse, fallback: string): void {
    this.actioningId.set(null);
    const body = error.error;
    if (body && typeof body === 'object') {
      const first = Object.values(body)[0];
      this.errorMessage.set(Array.isArray(first) ? String(first[0]) : String(first));
      return;
    }
    this.errorMessage.set(fallback);
  }
}
