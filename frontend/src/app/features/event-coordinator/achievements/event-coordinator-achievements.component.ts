import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { Achievement } from '../../../core/models/achievement.model';
import { AchievementService } from '../../../core/services/achievement.service';
import { EmptyStateComponent } from '../../../shared/empty-state/empty-state.component';

/**
 * Event Coordinator review of Faculty-created achievements, department-scoped by the backend.
 * Only PENDING_APPROVAL records are decidable; drafts a Faculty member has not
 * submitted yet are shown separately and carry no action buttons.
 */
@Component({
  selector: 'app-event-coordinator-achievements',
  standalone: true,
  imports: [DatePipe, FormsModule, RouterLink, EmptyStateComponent],
  templateUrl: './event-coordinator-achievements.component.html',
})
export class EventCoordinatorAchievementsComponent implements OnInit {
  readonly records = signal<Achievement[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);
  readonly actioningId = signal<number | null>(null);
  readonly rejectingId = signal<number | null>(null);
  rejectionReason = '';

  readonly pending = computed(() => this.records().filter((r) => r.status === 'PENDING_APPROVAL'));
  readonly decided = computed(() =>
    this.records().filter((r) => r.status === 'APPROVED' || r.status === 'REJECTED'),
  );

  constructor(private readonly achievementService: AchievementService) {}

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.achievementService.list().subscribe({
      next: (page) => {
        this.records.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load achievements.');
        this.loading.set(false);
      },
    });
  }

  approve(record: Achievement): void {
    if (this.actioningId() !== null) {
      return;
    }
    this.actioningId.set(record.id);
    this.errorMessage.set(null);
    this.achievementService.approve(record.id).subscribe({
      next: (updated) => this.applyDecision(updated),
      error: (error: HttpErrorResponse) => this.handleError(error, 'Unable to approve this achievement.'),
    });
  }

  startReject(record: Achievement): void {
    this.rejectingId.set(record.id);
    this.rejectionReason = '';
    this.errorMessage.set(null);
  }

  cancelReject(): void {
    this.rejectingId.set(null);
    this.rejectionReason = '';
  }

  confirmReject(record: Achievement): void {
    if (!this.rejectionReason.trim() || this.actioningId() !== null) {
      return;
    }
    this.actioningId.set(record.id);
    this.achievementService.reject(record.id, this.rejectionReason.trim()).subscribe({
      next: (updated) => {
        this.rejectingId.set(null);
        this.rejectionReason = '';
        this.applyDecision(updated);
      },
      error: (error: HttpErrorResponse) => this.handleError(error, 'Unable to reject this achievement.'),
    });
  }

  badgeClass(status: string): string {
    if (status === 'APPROVED') {
      return 'text-bg-success';
    }
    return status === 'REJECTED' ? 'text-bg-danger' : 'text-bg-warning';
  }

  private applyDecision(updated: Achievement): void {
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
