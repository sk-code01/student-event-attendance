import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ODRequest } from '../../../core/models/od.model';
import { OdService } from '../../../core/services/od.service';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';

/** Event Coordinator OD approval queue — department-scoped by the backend, independent of the
 * attendance queue. */
@Component({
  selector: 'app-event-coordinator-od',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink, EmptyStateComponent],
  templateUrl: './event-coordinator-od.component.html',
})
export class EventCoordinatorOdComponent implements OnInit {
  readonly records = signal<ODRequest[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly actioningId = signal<number | null>(null);
  readonly rejectingId = signal<number | null>(null);
  rejectionReason = '';

  readonly pending = computed(() => this.records().filter((r) => r.status === 'PENDING'));
  readonly decided = computed(() => this.records().filter((r) => r.status !== 'PENDING'));

  constructor(private readonly odService: OdService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.odService.list().subscribe({
      next: (page) => {
        this.records.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load OD requests.');
        this.loading.set(false);
      },
    });
  }

  approve(record: ODRequest): void {
    if (this.actioningId() !== null) {
      return;
    }
    this.actioningId.set(record.id);
    this.errorMessage.set(null);
    this.odService.approve(record.id).subscribe({
      next: (updated) => this.applyDecision(updated),
      error: (error: HttpErrorResponse) => this.handleError(error, 'Unable to approve this OD request.'),
    });
  }

  startReject(record: ODRequest): void {
    this.rejectingId.set(record.id);
    this.rejectionReason = '';
    this.errorMessage.set(null);
  }

  cancelReject(): void {
    this.rejectingId.set(null);
    this.rejectionReason = '';
  }

  confirmReject(record: ODRequest): void {
    if (!this.rejectionReason.trim() || this.actioningId() !== null) {
      return;
    }
    this.actioningId.set(record.id);
    this.odService.reject(record.id, this.rejectionReason.trim()).subscribe({
      next: (updated) => {
        this.rejectingId.set(null);
        this.rejectionReason = '';
        this.applyDecision(updated);
      },
      error: (error: HttpErrorResponse) => this.handleError(error, 'Unable to reject this OD request.'),
    });
  }

  badgeClass(status: string): string {
    if (status === 'APPROVED') {
      return 'text-bg-success';
    }
    return status === 'REJECTED' ? 'text-bg-danger' : 'text-bg-info';
  }

  private applyDecision(updated: ODRequest): void {
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
