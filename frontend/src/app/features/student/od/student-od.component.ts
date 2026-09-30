import { DatePipe } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ODRequest } from '../../../core/models/od.model';
import { OdService } from '../../../core/services/od.service';

/** Read-only view of the student's own OD requests and their outcomes. */
@Component({
  selector: 'app-student-od',
  standalone: true,
  imports: [DatePipe, RouterLink],
  template: `
    <div class="container py-4">
      <a routerLink="/student" class="small">&larr; Back to Student area</a>
      <h1 class="h4 mt-2 mb-1">My OD Requests</h1>
      <p class="text-muted small">
        On-Duty is a separate decision from attendance — approval of one says nothing about the other.
      </p>

      @if (errorMessage()) {
        <div class="alert alert-danger py-2 small">{{ errorMessage() }}</div>
      }

      @if (loading()) {
        <p class="text-muted small">Loading&hellip;</p>
      } @else if (records().length === 0) {
        <p class="text-muted small">No OD requests yet.</p>
      } @else {
        <div class="table-responsive">
          <table class="table align-middle">
            <thead>
              <tr>
                <th>Event</th>
                <th>Event date</th>
                <th>Reason requested</th>
                <th>Status</th>
                <th>Reviewed</th>
                <th>Reason (if rejected)</th>
              </tr>
            </thead>
            <tbody>
              @for (record of records(); track record.id) {
                <tr>
                  <td>{{ record.event.title }}</td>
                  <td class="small text-muted">{{ record.event.event_date | date: 'mediumDate' }}</td>
                  <td class="small">{{ record.reason }}</td>
                  <td><span class="badge" [class]="badgeClass(record.status)">{{ record.status }}</span></td>
                  <td class="small text-muted">
                    {{ record.reviewed_at ? (record.reviewed_at | date: 'medium') : '—' }}
                  </td>
                  <td class="small">{{ record.rejection_reason || '—' }}</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </div>
  `,
})
export class StudentOdComponent implements OnInit {
  readonly records = signal<ODRequest[]>([]);
  readonly loading = signal(true);
  readonly errorMessage = signal<string | null>(null);

  constructor(private readonly odService: OdService) {}

  ngOnInit(): void {
    this.odService.list().subscribe({
      next: (page) => {
        this.records.set(page.results);
        this.loading.set(false);
      },
      error: () => {
        this.errorMessage.set('Unable to load your OD requests.');
        this.loading.set(false);
      },
    });
  }

  badgeClass(status: string): string {
    if (status === 'APPROVED') {
      return 'text-bg-success';
    }
    return status === 'REJECTED' ? 'text-bg-danger' : 'text-bg-info';
  }
}
